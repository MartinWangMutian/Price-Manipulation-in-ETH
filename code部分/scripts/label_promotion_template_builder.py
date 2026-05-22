#!/usr/bin/env python3
"""Build a pending label-promotion decision template from trace queues."""

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


def exploit_decision(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "queue_id": item["queue_id"],
        "tx_hash": item["tx_hash"],
        "incident_id": item["incident_id"],
        "candidate_label": 1,
        "candidate_role": item.get("candidate_role"),
        "decision": "pending_trace",
        "promotion_status": "not_promoted",
        "required_evidence": [
            "historical trace replay ok",
            "raw_trace_ref exists",
            "rich graph replay exists",
            "analyst confirms incident linkage and role",
        ],
        "analyst": "TBD",
        "reviewed_at": null_json(),
        "notes": "",
    }


def normal_decision(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "queue_id": item["queue_id"],
        "tx_hash": item["tx_hash"],
        "incident_id": item.get("incident_id", "normal_candidate"),
        "candidate_label": 0,
        "candidate_role": "normal_candidate",
        "selection_bucket": item.get("selection_bucket"),
        "decision": "pending_trace",
        "promotion_status": "not_promoted",
        "required_evidence": [
            "historical trace replay ok",
            "raw_trace_ref exists when trace method returns details",
            "screened against known incidents, sanctions, and exploit labels",
            "analyst confirms normal_candidate role",
        ],
        "analyst": "TBD",
        "reviewed_at": null_json(),
        "notes": "",
    }


def null_json() -> None:
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build pending label promotion decisions.")
    parser.add_argument("--exploit-queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--normal-queue", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--out", default="data/training/label_promotion_decisions.seed.json")
    parser.add_argument("--report", default="ops/reports/label-promotion-template-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    exploit_queue = read_json(root / args.exploit_queue)
    normal_queue = read_json(root / args.normal_queue)
    exploit_items = [exploit_decision(item) for item in exploit_queue.get("items", [])]
    normal_items = [normal_decision(item) for item in normal_queue.get("items", [])]
    payload = {
        "schema_ver": "label-promotion-decisions.v1",
        "created_at": now_iso(),
        "status": "pending_trace_and_review",
        "training_ready": False,
        "exploit_decisions": exploit_items,
        "normal_decisions": normal_items,
    }
    write_json(root / args.out, payload)

    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "out": args.out,
        "exploit_decisions": len(exploit_items),
        "normal_decisions": len(normal_items),
        "training_ready": False,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
