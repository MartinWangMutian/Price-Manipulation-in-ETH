#!/usr/bin/env python3
"""Create AlertEvent replay records from risk-score events."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def severity_for(score: float) -> str:
    if score > 0.9:
        return "critical"
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "watch"
    return "low"


def event_id_for(risk_score: dict[str, Any]) -> str:
    seed = f"alert-event.v1:{risk_score['idempotency_key']}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def load_tx_index(root: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        data = read_json(path)
        tx_hash = data.get("tx_hash")
        if isinstance(tx_hash, str) and tx_hash not in index:
            index[tx_hash] = {"path": str(path), "record": data}
    return index


def evidence_refs(
    risk_score: dict[str, Any],
    graph_index: dict[str, dict[str, Any]],
    trace_index: dict[str, dict[str, Any]],
) -> list[str]:
    tx_hash = risk_score["tx_hash"]
    refs = [f"risk-score:{risk_score['event_id']}"]
    graph = graph_index.get(tx_hash)
    if graph is not None:
        graph_record = graph["record"]
        refs.append(f"graph:{graph_record.get('event_id')}")
        snapshot = graph_record.get("graph_snapshot_ref")
        if isinstance(snapshot, str):
            refs.append(f"graph-snapshot:{snapshot}")
    trace = trace_index.get(tx_hash)
    if trace is not None:
        refs.append(f"trace:{trace['record'].get('event_id')}")
    else:
        refs.append("trace:missing")
    refs.append("label:none")
    return refs


def build_alert(
    risk_score: dict[str, Any],
    routing: dict[str, Any],
    graph_index: dict[str, dict[str, Any]],
    trace_index: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    score = float(risk_score["score"])
    routed_severity = severity_for(score)
    warnings: list[str] = []
    if risk_score.get("severity") != routed_severity:
        warnings.append(
            f"severity mismatch: risk={risk_score.get('severity')} routed={routed_severity}"
        )
    event_id = event_id_for(risk_score)
    actions = list(routing["actions"].get(routed_severity, []))
    alert = {
        "event_id": event_id,
        "schema_ver": "alert-event.v1",
        "chain_id": risk_score["chain_id"],
        "created_at": now_iso(),
        "idempotency_key": f"{risk_score['idempotency_key']}:alert-event.v1",
        "alert_id": f"alert:{risk_score['tx_hash']}",
        "tx_hash": risk_score["tx_hash"],
        "score": score,
        "severity": routed_severity,
        "reasons": risk_score.get("reasons", []),
        "evidence_refs": evidence_refs(risk_score, graph_index, trace_index),
        "suggested_actions": actions,
        "alert_version": routing["alert_version"],
        "review_state": "new",
    }
    return alert, warnings


def replay_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "replay"
        / "alert-event.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create alert events from risk scores.")
    parser.add_argument("--risk-input", default="data/replay/risk-score.v1")
    parser.add_argument("--graph-input", default="data/replay/graph-inference.v1")
    parser.add_argument("--trace-input", default="data/replay/trace-bundle.v1")
    parser.add_argument("--config", default="config/alert_routing.json")
    parser.add_argument("--out", default="ops/reports/alert-orchestrator.latest.json")
    parser.add_argument("--audit-log", default="ops/audit/alert-orchestrator.jsonl")
    parser.add_argument("--write-replay", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    routing = read_json(root / args.config)
    graph_index = load_tx_index(root / args.graph_input)
    trace_index = load_tx_index(root / args.trace_input)
    seen_input_keys: set[str] = set()
    skipped_duplicates = 0
    alerts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    severity_counts = Counter()
    action_counts = Counter()

    for path in iter_json_files(root / args.risk_input):
        try:
            risk_score = read_json(path)
            key = risk_score.get("idempotency_key")
            if not isinstance(key, str):
                errors.append({"path": str(path), "error": "missing idempotency_key"})
                continue
            if key in seen_input_keys:
                skipped_duplicates += 1
                continue
            seen_input_keys.add(key)
            alert, alert_warnings = build_alert(risk_score, routing, graph_index, trace_index)
            alerts.append(alert)
            severity_counts[alert["severity"]] += 1
            for action in alert["suggested_actions"]:
                action_counts[action] += 1
            if alert_warnings:
                warnings.append({"path": str(path), "warnings": alert_warnings})
            if args.write_replay:
                write_json(replay_output_path(root, alert), alert)
            append_jsonl(
                root / args.audit_log,
                {
                    "created_at": now_iso(),
                    "stage": "alert-orchestrator",
                    "risk_event_id": risk_score.get("event_id"),
                    "alert_event_id": alert["event_id"],
                    "tx_hash": alert["tx_hash"],
                    "severity": alert["severity"],
                    "score": alert["score"],
                    "actions": alert["suggested_actions"],
                },
            )
        except Exception as exc:  # noqa: BLE001 - audit report should keep scanning.
            errors.append({"path": str(path), "error": str(exc)})

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "risk_input": args.risk_input,
        "graph_input": args.graph_input,
        "trace_input": args.trace_input,
        "files_seen": len(iter_json_files(root / args.risk_input)),
        "unique_risk_scores": len(seen_input_keys),
        "skipped_duplicate_risk_scores": skipped_duplicates,
        "alerts_generated": len(alerts),
        "alerts_written": len(alerts) if args.write_replay else 0,
        "severity_counts": dict(sorted(severity_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "audit_log": args.audit_log,
        "warnings": warnings,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
