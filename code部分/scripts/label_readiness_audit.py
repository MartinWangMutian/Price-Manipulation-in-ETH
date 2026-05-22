#!/usr/bin/env python3
"""Audit exploit and normal label backlog readiness."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def status(report: Any | None) -> str:
    if report is None:
        return "missing"
    return str(report.get("status", "unknown"))


def dry_run_ok(report: Any | None, expected_count: int) -> bool:
    if report is None:
        return False
    return (
        report.get("status") == "dry_run_ok"
        and report.get("dry_run") is True
        and report.get("queue_items_seen") == expected_count
        and not report.get("validation_errors")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit label backlog readiness.")
    parser.add_argument("--out", default="ops/reports/label-readiness-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    exploit = read_json_or_none(root / "ops/reports/replay-label-candidates-check.latest.json")
    exploit_trace = read_json_or_none(root / "ops/reports/historical-trace-replay.latest.json")
    normal = read_json_or_none(root / "ops/reports/normal-replay-candidates-check.latest.json")
    normal_trace = read_json_or_none(root / "ops/reports/normal-historical-trace-replay.latest.json")
    training = read_json_or_none(root / "ops/reports/training-dataset-check.latest.json")
    promotion = read_json_or_none(root / "ops/reports/label-promotion-audit.latest.json")

    exploit_count = int(exploit.get("candidate_transactions", 0)) if exploit else 0
    normal_count = int(normal.get("candidate_count", 0)) if normal else 0
    checks = [
        {
            "name": "exploit_candidate_hashes",
            "ok": status(exploit) == "ok" and exploit_count > 0,
            "evidence": {
                "status": status(exploit),
                "candidate_transactions": exploit_count,
                "missing_ethereum_candidate_incidents": exploit.get("missing_ethereum_candidate_incidents", []) if exploit else None,
            },
        },
        {
            "name": "exploit_trace_queue_dry_run",
            "ok": dry_run_ok(exploit_trace, exploit_count),
            "evidence": {
                "status": status(exploit_trace),
                "queue_items_seen": exploit_trace.get("queue_items_seen") if exploit_trace else None,
            },
        },
        {
            "name": "normal_candidate_hashes",
            "ok": status(normal) == "ok" and normal_count >= 50,
            "evidence": {
                "status": status(normal),
                "candidate_count": normal_count,
                "bucket_counts": normal.get("bucket_counts", {}) if normal else None,
            },
        },
        {
            "name": "normal_trace_queue_dry_run",
            "ok": dry_run_ok(normal_trace, normal_count),
            "evidence": {
                "status": status(normal_trace),
                "queue_items_seen": normal_trace.get("queue_items_seen") if normal_trace else None,
            },
        },
        {
            "name": "training_dataset_manifest",
            "ok": status(training) == "ok" and training.get("training_ready") is False if training else False,
            "evidence": {
                "status": status(training),
                "training_ready": training.get("training_ready") if training else None,
            },
        },
        {
            "name": "promotion_decision_template",
            "ok": status(promotion) == "ok" and promotion.get("promoted_markers") == 0 if promotion else False,
            "evidence": {
                "status": status(promotion),
                "promoted_markers": promotion.get("promoted_markers") if promotion else None,
                "decision_counts": promotion.get("decision_counts") if promotion else None,
            },
        },
    ]

    trace_ready = all(check["ok"] for check in checks[:4])
    training_ready = False
    blockers = []
    if not trace_ready:
        blockers.append("candidate queues or dry-run validation are incomplete")
    blockers.extend(
        [
            "ETH_MAIN_HTTP_URL trace endpoint is required for real replay",
            "candidate traces must be analyst-promoted before labels are training-ready",
            "negative candidates require screening against incident/sanctions/exploit labels",
        ]
    )

    report = {
        "checked_at": now_iso(),
        "status": "trace_ready" if trace_ready else "not_ready",
        "trace_ready": trace_ready,
        "training_ready": training_ready,
        "exploit_candidate_transactions": exploit_count,
        "normal_candidate_transactions": normal_count,
        "total_trace_queue_items": exploit_count + normal_count,
        "pending_promotion_decisions": (promotion.get("decision_counts", {}) or {}).get("pending_trace", 0) if promotion else 0,
        "promoted_markers": promotion.get("promoted_markers", 0) if promotion else 0,
        "checks": checks,
        "blockers": blockers,
        "next_commands_after_endpoint": [
            "python3 scripts/historical_trace_replay.py --queue data/training/trace_replay_queue.v1.json --method auto --out ops/reports/historical-trace-replay.latest.json",
            "python3 scripts/historical_trace_replay.py --queue data/training/normal_trace_replay_queue.v1.json --method auto --out ops/reports/normal-historical-trace-replay.latest.json",
        ],
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if trace_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
