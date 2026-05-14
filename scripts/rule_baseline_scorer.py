#!/usr/bin/env python3
"""Offline rule-baseline scorer for graph-inference replay records."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def event_id_for(graph: dict[str, Any]) -> str:
    seed = f"risk-score.v1:{graph['idempotency_key']}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def severity_for(score: float, thresholds: dict[str, Any]) -> str:
    critical = float(thresholds.get("critical", 0.9))
    high = float(thresholds.get("high", 0.75))
    watch = float(thresholds.get("watch", 0.5))
    if score > critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= watch:
        return "watch"
    return "low"


def protocol_roles(graph: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for node in graph.get("nodes", []):
        if isinstance(node, dict) and node.get("node_type") == "protocol":
            for role in node.get("roles", []):
                if isinstance(role, str):
                    roles.add(role)
    return roles


def abnormal_profit_path(graph: dict[str, Any], min_abs_amount: float) -> bool:
    # Conservative placeholder: only fires when normalized transfer edges produce
    # large net positive flow for an address after the graph has protocol context.
    has_protocol = any(
        isinstance(node, dict) and node.get("node_type") == "protocol"
        for node in graph.get("nodes", [])
    )
    if not has_protocol:
        return False
    net_by_address_asset: dict[tuple[str, str], float] = defaultdict(float)
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict) or edge.get("edge_type") != "transfer":
            continue
        asset = edge.get("asset_node")
        amount_norm = edge.get("amount_norm")
        if asset is None or amount_norm is None:
            continue
        try:
            amount = float(amount_norm)
        except (TypeError, ValueError):
            continue
        sender = edge.get("from_node")
        receiver = edge.get("to_node")
        if isinstance(sender, str):
            net_by_address_asset[(sender, asset)] -= amount
        if isinstance(receiver, str):
            net_by_address_asset[(receiver, asset)] += amount
    return any(value >= min_abs_amount for value in net_by_address_asset.values())


def oracle_read_write_same_tx(graph: dict[str, Any]) -> bool:
    roles = protocol_roles(graph)
    protocol_touch = bool(roles & {"pool", "router", "lending_market", "liquidation_module"})
    return "oracle" in roles and protocol_touch


def excessive_slippage(graph: dict[str, Any], min_slippage_bps: float) -> bool:
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        slippage = edge.get("slippage_bps")
        try:
            if slippage is not None and float(slippage) >= min_slippage_bps:
                return True
        except (TypeError, ValueError):
            continue
    return False


def thin_liquidity_trade(graph: dict[str, Any], max_liquidity_usd: float) -> bool:
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        liquidity = node.get("liquidity_usd")
        try:
            if liquidity is not None and float(liquidity) <= max_liquidity_usd:
                return True
        except (TypeError, ValueError):
            continue
    return False


def flash_loan_path(graph: dict[str, Any], selector_hints: list[str]) -> bool:
    lowered_hints = [hint.lower() for hint in selector_hints]
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict) or edge.get("edge_type") != "call":
            continue
        name = str(edge.get("function_name") or edge.get("function_signature") or "").lower()
        if any(hint in name for hint in lowered_hints):
            return True
    return False


def score_graph(graph: dict[str, Any], config: dict[str, Any]) -> tuple[float, list[str]]:
    rules = config["rules"]
    reasons: list[str] = []
    score = 0.0

    abnormal_cfg = rules["abnormal_profit_path"]
    if abnormal_profit_path(graph, float(abnormal_cfg["min_abs_amount_norm"])):
        score += float(abnormal_cfg["weight"])
        reasons.append(abnormal_cfg["reason_code"])

    oracle_cfg = rules["oracle_read_write_same_tx"]
    if oracle_read_write_same_tx(graph):
        score += float(oracle_cfg["weight"])
        reasons.append(oracle_cfg["reason_code"])

    slippage_cfg = rules["excessive_slippage"]
    if excessive_slippage(graph, float(slippage_cfg["min_slippage_bps"])):
        score += float(slippage_cfg["weight"])
        reasons.append(slippage_cfg["reason_code"])

    liquidity_cfg = rules["thin_liquidity_trade"]
    if thin_liquidity_trade(graph, float(liquidity_cfg["max_liquidity_usd"])):
        score += float(liquidity_cfg["weight"])
        reasons.append(liquidity_cfg["reason_code"])

    flash_cfg = rules["flash_loan_path"]
    if flash_loan_path(graph, list(flash_cfg["selector_hints"])):
        score += float(flash_cfg["weight"])
        reasons.append(flash_cfg["reason_code"])

    no_edges = not graph.get("edges")
    if no_edges:
        fallback = config["fallback"]
        score = max(score, float(fallback["no_rich_evidence_score"]))
        reasons.append(fallback["no_rich_evidence_reason"])
    if "trace_unsupported" in graph.get("feature_missing_flags", []):
        reasons.append("FEATURE_TRACE_UNSUPPORTED")

    return min(round(score, 6), 1.0), sorted(set(reasons))


def build_risk_score(graph: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    score, reasons = score_graph(graph, config)
    thresholds = config["severity_thresholds"]
    return {
        "event_id": event_id_for(graph),
        "schema_ver": "risk-score.v1",
        "chain_id": graph["chain_id"],
        "created_at": now_iso(),
        "idempotency_key": f"{graph['idempotency_key']}:risk-score.v1",
        "tx_hash": graph["tx_hash"],
        "score": score,
        "severity": severity_for(score, thresholds),
        "reasons": reasons,
        "model_version": config["model_version"],
        "feature_ver": graph["feature_ver"],
        "threshold_profile": config["threshold_profile"],
        "model_reject_reason": config["fallback"]["model_reject_reason"],
    }


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


def rule_hit_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "rule-hits"
        / "risk-score.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rule-baseline scoring on graph replay files.")
    parser.add_argument("--input", default="data/replay/graph-inference.v1")
    parser.add_argument("--config", default="config/rule_baseline.json")
    parser.add_argument("--out", default="ops/reports/rule-baseline-scorer.latest.json")
    parser.add_argument("--write-replay", action="store_true")
    parser.add_argument("--write-hit-samples", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    config = read_json(root / args.config)
    seen_input_keys: set[str] = set()
    skipped_duplicates = 0
    scores: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    severity_counts = Counter()
    reason_counts = Counter()

    for path in iter_json_files(root / args.input):
        try:
            graph = read_json(path)
            key = graph.get("idempotency_key")
            if not isinstance(key, str):
                errors.append({"path": str(path), "error": "missing idempotency_key"})
                continue
            if key in seen_input_keys:
                skipped_duplicates += 1
                continue
            seen_input_keys.add(key)
            record = build_risk_score(graph, config)
            scores.append(record)
            severity_counts[record["severity"]] += 1
            for reason in record["reasons"]:
                reason_counts[reason] += 1
            if args.write_replay:
                write_json(replay_output_path(root, record), record)
            rule_reasons = [
                reason
                for reason in record["reasons"]
                if reason.startswith("RULE_") and reason != config["fallback"]["no_rich_evidence_reason"]
            ]
            if args.write_hit_samples and rule_reasons:
                write_json(rule_hit_path(root, record), {"risk_score": record, "graph": graph})
        except Exception as exc:  # noqa: BLE001 - report all scoring failures.
            errors.append({"path": str(path), "error": str(exc)})

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "input": args.input,
        "files_seen": len(iter_json_files(root / args.input)),
        "unique_graphs": len(seen_input_keys),
        "skipped_duplicate_graphs": skipped_duplicates,
        "risk_scores_written": len(scores) if args.write_replay else 0,
        "scores_generated": len(scores),
        "severity_counts": dict(sorted(severity_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "model_version": config["model_version"],
        "threshold_profile": config["threshold_profile"],
        "model_reject_reason": config["fallback"]["model_reject_reason"],
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
