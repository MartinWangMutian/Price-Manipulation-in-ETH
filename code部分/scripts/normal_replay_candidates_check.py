#!/usr/bin/env python3
"""Validate normal replay candidates before negative-label promotion."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


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


def positive_hashes(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = read_json(path)
    hashes = set()
    for incident in payload.get("positive_candidates", []):
        for tx in incident.get("candidate_transactions", []):
            tx_hash = tx.get("tx_hash")
            if isinstance(tx_hash, str):
                hashes.add(tx_hash.lower())
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate normal replay candidate set.")
    parser.add_argument("--candidates", default="data/training/normal_replay_candidates.seed.json")
    parser.add_argument("--queue", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--positive-candidates", default="data/training/replay_label_candidates.seed.json")
    parser.add_argument("--min-count", type=int, default=50)
    parser.add_argument("--out", default="ops/reports/normal-replay-candidates-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    candidates = read_json(root / args.candidates)
    queue = read_json(root / args.queue)
    positives = positive_hashes(root / args.positive_candidates)
    errors: list[str] = []
    tx_hashes: set[str] = set()
    buckets = Counter()

    items = candidates.get("items", [])
    queue_items = queue.get("items", [])
    if len(items) < args.min_count:
        errors.append(f"selected candidate count below min_count {args.min_count}")
    if len(queue_items) != len(items):
        errors.append("queue item count does not match candidate item count")

    for item in items:
        tx_hash = item.get("tx_hash", "")
        if not TX_RE.match(tx_hash):
            errors.append(f"invalid tx_hash {tx_hash}")
            continue
        tx_hash_lower = tx_hash.lower()
        if tx_hash_lower in tx_hashes:
            errors.append(f"duplicate tx_hash {tx_hash}")
        tx_hashes.add(tx_hash_lower)
        if tx_hash_lower in positives:
            errors.append(f"normal candidate overlaps positive candidate {tx_hash}")
        if item.get("candidate_label") != 0:
            errors.append(f"{tx_hash} candidate_label must be 0")
        if item.get("review_status") != "needs_trace_replay_and_screening":
            errors.append(f"{tx_hash} has invalid review_status")
        if item.get("block_number") is None:
            errors.append(f"{tx_hash} missing mined block_number")
        buckets[item.get("selection_bucket", "unknown")] += 1

    queue_hashes = {item.get("tx_hash", "").lower() for item in queue_items}
    if queue_hashes != tx_hashes:
        errors.append("queue tx_hash set does not match candidate tx_hash set")

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "candidate_count": len(items),
        "queue_count": len(queue_items),
        "bucket_counts": dict(sorted(buckets.items())),
        "training_ready": False,
        "promotion_required": True,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
