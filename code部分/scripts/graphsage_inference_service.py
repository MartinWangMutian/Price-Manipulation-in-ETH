#!/usr/bin/env python3
"""Batch GraphSAGE inference service entry point with explicit rule fallback metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphsage_model import (
    CashFlowGraphSAGE,
    GraphSAGEConfig,
    dependency_status,
    graph_tensors,
    load_graph_records,
    load_manifest,
    require_torch_stack,
)
from rule_baseline_scorer import evaluate_graph


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def event_id_for(graph: dict[str, Any], model_version: str) -> str:
    seed = f"risk-score.v1:{graph['idempotency_key']}:{model_version}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def severity_for(score: float, thresholds: dict[str, Any]) -> str:
    if score > float(thresholds.get("critical", 0.9)):
        return "critical"
    if score >= float(thresholds.get("high", 0.75)):
        return "high"
    if score >= float(thresholds.get("watch", 0.5)):
        return "watch"
    return "low"


def risk_record(
    graph: dict[str, Any],
    score: float,
    model_version: str,
    threshold_profile: str,
    thresholds: dict[str, Any],
    reject_reason: str | None,
    reasons: list[str] | None = None,
    rule_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    record = {
        "event_id": event_id_for(graph, model_version),
        "schema_ver": "risk-score.v1",
        "chain_id": graph["chain_id"],
        "created_at": now_iso(),
        "idempotency_key": f"{graph['idempotency_key']}:{model_version}:risk-score.v1",
        "tx_hash": graph["tx_hash"],
        "score": round(score, 6),
        "severity": severity_for(score, thresholds),
        "reasons": reasons or (
            ["MODEL_GRAPHSAGE"] if reject_reason is None else ["MODEL_FALLBACK_RULE_BASELINE"]
        ),
        "model_version": model_version,
        "feature_ver": graph["feature_ver"],
        "threshold_profile": threshold_profile,
        "model_reject_reason": reject_reason,
    }
    if rule_scores is not None:
        record["rule_scores"] = rule_scores
    return record


def rule_fallback_record(
    graph: dict[str, Any], fallback: dict[str, Any], reject_reason: str
) -> dict[str, Any]:
    score, reasons, rule_scores = evaluate_graph(graph, fallback)
    return risk_record(
        graph,
        score,
        fallback["model_version"],
        fallback["threshold_profile"],
        fallback["severity_thresholds"],
        reject_reason,
        sorted(set(reasons + ["MODEL_FALLBACK_RULE_BASELINE"])),
        rule_scores,
    )


def replay_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "replay"
        / "risk-score.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GraphSAGE inference over graph replay files.")
    parser.add_argument("--input", default="data/replay/graph-inference.v1")
    parser.add_argument("--model-dir", default="models/graphsage/latest")
    parser.add_argument("--fallback-config", default="config/rule_baseline.json")
    parser.add_argument("--out", default="ops/reports/graphsage-inference.latest.json")
    parser.add_argument("--write-replay", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    graphs = load_graph_records(root / args.input)
    fallback = read_json(root / args.fallback_config)
    thresholds = fallback["severity_thresholds"]
    manifest_path = root / args.model_dir / "manifest.json"
    checkpoint_path = root / args.model_dir / "model.pt"
    dependencies = dependency_status()
    reject_reason = None
    manifest: dict[str, Any] | None = None

    if not manifest_path.exists() or not checkpoint_path.exists():
        reject_reason = "graphsage_model_artifact_missing"
    elif not all(dependencies.values()):
        reject_reason = "torch_or_torch_geometric_missing"
    else:
        manifest = load_manifest(manifest_path)

    records: list[dict[str, Any]] = []
    if reject_reason is not None:
        for graph in graphs:
            records.append(rule_fallback_record(graph, fallback, reject_reason))
    else:
        assert manifest is not None
        torch, _, _, _ = require_torch_stack()
        config = GraphSAGEConfig(
            model_version=manifest["model_version"],
            feature_ver=manifest["feature_ver"],
            label_snapshot=manifest["label_snapshot"],
            threshold_profile=manifest["threshold_profile"],
            input_dim=int(manifest["input_dim"]),
            hidden_dim=int(manifest["hidden_dim"]),
            dropout=float(manifest["dropout"]),
            num_layers=int(manifest["num_layers"]),
            aggregator=manifest["aggregator"],
        )
        model = CashFlowGraphSAGE(config)
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        for graph in graphs:
            if graph.get("feature_ver") != config.feature_ver:
                records.append(rule_fallback_record(graph, fallback, "feature_version_mismatch"))
                continue
            x, edge_index, batch = graph_tensors([graph])
            with torch.no_grad():
                score = float(model(x, edge_index, batch)[0].cpu().item())
            records.append(
                risk_record(
                    graph,
                    score,
                    config.model_version,
                    config.threshold_profile,
                    thresholds,
                    None,
                )
            )

    if args.write_replay:
        for record in records:
            write_json(replay_output_path(root, record), record)
    report = {
        "checked_at": now_iso(),
        "status": "ok" if reject_reason is None else "degraded",
        "graphs_seen": len(graphs),
        "scores_built": len(records),
        "dependencies": dependencies,
        "model_dir": args.model_dir,
        "model_reject_reason": reject_reason,
        "write_replay": args.write_replay,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
