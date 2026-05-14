#!/usr/bin/env python3
"""Audit validation metrics checklist against current reports."""

from __future__ import annotations

import argparse
import json
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


def item(name: str, ok: bool, target: Any, observed: Any, note: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "target": target,
        "observed": observed,
        "note": note,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit validation metrics.")
    parser.add_argument("--out", default="ops/reports/validation-metrics-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    load = read_json(root / "ops/reports/load-test-replay.latest.json")
    offline = read_json(root / "ops/reports/offline-evaluation.latest.json")
    alert_check = read_json(root / "ops/reports/alert-replay-check.latest.json")
    console_check = read_json(root / "ops/reports/analyst-console-view-check.latest.json")

    graph_p95 = load.get("graph_builder_latency_ms", {}).get("p95")
    model_p95 = load.get("model_inference_latency_ms", {}).get("p95")
    e2e_p95 = load.get("end_to_end_detection_latency_ms", {}).get("p95")
    e2e_p99 = load.get("end_to_end_detection_latency_ms", {}).get("p99")
    evidence = offline.get("evidence_ref_validity", {})
    duplicate_keys = alert_check.get("duplicate_idempotency_keys", [])

    metrics = [
        item("roc_auc", False, ">=0.95", None, "GraphSAGE training is blocked"),
        item("pr_auc_lift", False, "project baseline lift", None, "GraphSAGE training is blocked"),
        item("recall_at_fpr_3pct", False, ">=0.80", None, "GraphSAGE training is blocked"),
        item("lead_time", False, "measured", offline.get("lead_time"), "requires labeled attack timeline"),
        item("calibration_error", False, "measured", None, "requires labeled validation set"),
        item("pending_enqueue_p95", False, "<=100ms", None, "live stream load test required"),
        item("trace_p95", False, "<=1.5s", None, "Geth/Erigon trace endpoint required"),
        item("graph_build_p95", bool(graph_p95 is not None and graph_p95 <= 300), "<=300ms", graph_p95),
        item("model_inference_p95", bool(model_p95 is not None and model_p95 <= 50), "<=50ms", model_p95),
        item(
            "end_to_end_detection_p95",
            False,
            "<3s",
            e2e_p95,
            "current value is replay timestamp gap, not live SLO",
        ),
        item(
            "end_to_end_detection_p99",
            False,
            "<8s",
            e2e_p99,
            "current value is replay timestamp gap, not live SLO",
        ),
        item(
            "high_critical_graph_evidence_coverage",
            False,
            "100%",
            offline.get("high_critical_graph_evidence_coverage"),
            "no high/critical rich graph samples",
        ),
        item(
            "high_critical_explanation_availability",
            False,
            "100%",
            offline.get("high_critical_explanation_availability"),
            "no high/critical rich graph samples",
        ),
        item(
            "evidence_ref_validity",
            evidence.get("coverage") == 1.0,
            "100%",
            evidence,
        ),
        item(
            "duplicate_alert_rate",
            not duplicate_keys,
            "near 0",
            {"duplicate_idempotency_keys": duplicate_keys},
        ),
        item(
            "analyst_review_completion_trace",
            console_check.get("status") == "ok",
            "all states leave audit trail",
            {
                "detail_views": console_check.get("detail_views"),
                "audit_trail_lines": console_check.get("audit_trail_lines"),
            },
        ),
    ]
    report = {
        "checked_at": now_iso(),
        "status": "pass" if all(metric["ok"] for metric in metrics) else "not_pass",
        "metrics": metrics,
        "summary": {
            "passed": sum(1 for metric in metrics if metric["ok"]),
            "failed": sum(1 for metric in metrics if not metric["ok"]),
        },
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
