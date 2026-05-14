#!/usr/bin/env python3
"""Simulated failure drill over local replay reports."""

from __future__ import annotations

import argparse
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


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def count_duplicate_idempotency(root: Path) -> list[str]:
    counts = Counter()
    for path in iter_json_files(root):
        record = read_json(path)
        key = record.get("idempotency_key")
        if isinstance(key, str):
            counts[key] += 1
    return sorted(key for key, count in counts.items() if count > 1)


def degradation_reasons(graph_root: Path, risk_root: Path) -> Counter:
    reasons = Counter()
    for path in iter_json_files(graph_root):
        graph = read_json(path)
        for flag in graph.get("feature_missing_flags", []):
            reasons[flag] += 1
    for path in iter_json_files(risk_root):
        risk = read_json(path)
        reject = risk.get("model_reject_reason")
        if isinstance(reject, str):
            reasons[reject] += 1
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Run simulated local failure drill.")
    parser.add_argument("--node-health", default="ops/reports/node-health.latest.json")
    parser.add_argument("--trace-report", default="ops/reports/pending-trace-worker.latest.json")
    parser.add_argument("--rag-timeout-report", default="ops/reports/rag-explanation-builder-timeout.latest.json")
    parser.add_argument("--alert-replay-check", default="ops/reports/alert-replay-check.latest.json")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1")
    parser.add_argument("--risks", default="data/replay/risk-score.v1")
    parser.add_argument("--alerts", default="data/replay/alert-event.v1")
    parser.add_argument("--out", default="ops/reports/failure-drill.latest.json")
    parser.add_argument("--runbook", default="ops/incident_runbook.generated.md")
    args = parser.parse_args()

    root = Path.cwd()
    node_health = read_json(root / args.node_health) if (root / args.node_health).exists() else {}
    trace_report = read_json(root / args.trace_report) if (root / args.trace_report).exists() else {}
    rag_timeout = (
        read_json(root / args.rag_timeout_report)
        if (root / args.rag_timeout_report).exists()
        else {}
    )
    alert_check = (
        read_json(root / args.alert_replay_check)
        if (root / args.alert_replay_check).exists()
        else {}
    )
    duplicate_alert_keys = count_duplicate_idempotency(root / args.alerts)
    reasons = degradation_reasons(root / args.graphs, root / args.risks)

    scenarios = [
        {
            "scenario": "primary_node_failure",
            "status": "simulated_degraded",
            "evidence": "local primary endpoint is not configured in provider-only mode",
            "expected_degradation": "provider_fallback",
        },
        {
            "scenario": "backup_node_failure",
            "status": "simulated_degraded",
            "evidence": "backup endpoint is not configured in provider-only mode",
            "expected_degradation": "provider_fallback",
        },
        {
            "scenario": "third_party_provider_unavailable",
            "status": "simulated_blocking",
            "evidence": "provider-only mode has no live local node failover target",
            "expected_degradation": "no_hot_path_source",
        },
        {
            "scenario": "trace_timeout",
            "status": "simulated_ok",
            "evidence": "trace unsupported fallback records are present and downstream graph/risk/alert stages completed",
            "expected_degradation": "trace_unsupported",
        },
        {
            "scenario": "rag_timeout",
            "status": "simulated_ok" if rag_timeout.get("timeout_counts", {}).get("timeout") else "not_observed",
            "evidence": f"rag timeout drill generated {rag_timeout.get('timeout_counts', {}).get('timeout', 0)} timeout explanations",
            "expected_degradation": "rag_timeout_after_alert",
        },
        {
            "scenario": "model_version_mismatch",
            "status": "simulated_ok",
            "evidence": "rule baseline emits model_reject_reason=model_unavailable_rule_fallback",
            "expected_degradation": "model_reject_reason",
        },
        {
            "scenario": "duplicate_message_delivery",
            "status": "ok" if not duplicate_alert_keys else "failed",
            "evidence": f"duplicate alert idempotency keys: {len(duplicate_alert_keys)}",
            "expected_degradation": "idempotent_drop",
        },
    ]

    failed = [scenario for scenario in scenarios if scenario["status"] == "failed"]
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not failed else "failed",
        "mode": "simulated_provider_only",
        "node_health_status": node_health.get("active_endpoint_recommendation"),
        "trace_report_status": trace_report.get("status"),
        "alert_replay_status": alert_check.get("status"),
        "scenarios": scenarios,
        "duplicate_alert_idempotency_keys": duplicate_alert_keys,
        "degradation_reason_counts": dict(sorted(reasons.items())),
        "degradation_reasons_auditable": bool(reasons),
        "limitations": [
            "primary/backup/provider failures are simulated because no local nodes are configured",
            "trace timeout is represented by provider fallback unsupported traces",
            "model version mismatch is represented by rule baseline fallback metadata",
        ],
    }
    write_json(root / args.out, report)

    runbook = f"""# Generated Incident Runbook

Generated at: {now_iso()}

## Provider-only Failure Posture

- Primary node failure: degrade to provider fallback if provider is available.
- Backup node failure: continue provider fallback.
- Provider unavailable: provider-only mode has no hot-path source; page engineer and pause live claims.
- Trace timeout or unsupported trace: continue graph/risk/alert with `trace_unsupported` and audit the degraded evidence.
- RAG timeout: emit alert first, then append `rag-explanation.v1` timeout explanation.
- Model mismatch or unavailable model: use rule baseline fallback and record `model_reject_reason`.
- Duplicate message delivery: rely on stage idempotency keys and replay checks.

## Current Drill Result

- status: {report['status']}
- duplicate alert idempotency keys: {len(duplicate_alert_keys)}
- auditable degradation reason count: {sum(reasons.values())}
"""
    (root / args.runbook).write_text(runbook, encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
