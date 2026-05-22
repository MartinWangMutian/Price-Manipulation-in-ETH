#!/usr/bin/env python3
"""Audit label-promotion decisions for premature training-label promotion."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
VALID_PENDING = {"pending_trace", "pending_review", "rejected", "promoted"}


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


def queue_ids(path: Path) -> set[str]:
    payload = read_json(path)
    return {item["queue_id"] for item in payload.get("items", [])}


def audit_decision(item: dict[str, Any], expected_label: int, queue_ids_seen: set[str]) -> list[str]:
    errors = []
    if item.get("queue_id") not in queue_ids_seen:
        errors.append(f"unknown queue_id {item.get('queue_id')}")
    tx_hash = item.get("tx_hash")
    if not isinstance(tx_hash, str) or not TX_RE.match(tx_hash):
        errors.append(f"invalid tx_hash {tx_hash}")
    if item.get("candidate_label") != expected_label:
        errors.append(f"{tx_hash} candidate_label mismatch")
    if item.get("decision") not in VALID_PENDING:
        errors.append(f"{tx_hash} invalid decision {item.get('decision')}")
    if item.get("decision") == "promoted" or item.get("promotion_status") == "promoted":
        if item.get("analyst") in {"", "TBD", None}:
            errors.append(f"{tx_hash} promoted without analyst")
        if not item.get("reviewed_at"):
            errors.append(f"{tx_hash} promoted without reviewed_at")
        if not item.get("trace_bundle_ref"):
            errors.append(f"{tx_hash} promoted without trace_bundle_ref")
        if not item.get("graph_ref"):
            errors.append(f"{tx_hash} promoted without graph_ref")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit label promotion decisions.")
    parser.add_argument("--decisions", default="data/training/label_promotion_decisions.seed.json")
    parser.add_argument("--exploit-queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--normal-queue", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--out", default="ops/reports/label-promotion-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    decisions = read_json(root / args.decisions)
    exploit_queue_ids = queue_ids(root / args.exploit_queue)
    normal_queue_ids = queue_ids(root / args.normal_queue)
    errors: list[str] = []
    decision_counts = Counter()
    promotion_counts = Counter()

    for item in decisions.get("exploit_decisions", []):
        errors.extend(audit_decision(item, 1, exploit_queue_ids))
        decision_counts[item.get("decision", "unknown")] += 1
        promotion_counts[item.get("promotion_status", "unknown")] += 1
    for item in decisions.get("normal_decisions", []):
        errors.extend(audit_decision(item, 0, normal_queue_ids))
        decision_counts[item.get("decision", "unknown")] += 1
        promotion_counts[item.get("promotion_status", "unknown")] += 1

    promoted = decision_counts.get("promoted", 0) + promotion_counts.get("promoted", 0)
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "training_ready": promoted > 0 and not errors,
        "exploit_decisions": len(decisions.get("exploit_decisions", [])),
        "normal_decisions": len(decisions.get("normal_decisions", [])),
        "decision_counts": dict(sorted(decision_counts.items())),
        "promotion_counts": dict(sorted(promotion_counts.items())),
        "promoted_markers": promoted,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
