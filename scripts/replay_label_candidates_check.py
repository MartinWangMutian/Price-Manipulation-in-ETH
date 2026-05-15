#!/usr/bin/env python3
"""Validate replay label candidate seeds before they feed trace replay."""

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


def read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    return read_json(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate replay label candidates.")
    parser.add_argument("--candidates", default="data/training/replay_label_candidates.seed.json")
    parser.add_argument("--incidents", default="data/training/positive_incidents.seed.json")
    parser.add_argument("--normal-candidates", default="data/training/normal_replay_candidates.seed.json")
    parser.add_argument("--out", default="ops/reports/replay-label-candidates-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    candidates = read_json(root / args.candidates)
    incidents = read_json(root / args.incidents).get("incidents", [])
    incident_ids = {incident["incident_id"]: incident for incident in incidents}
    ethereum_incident_ids = {iid for iid, incident in incident_ids.items() if incident.get("chain") == "ethereum"}

    errors: list[str] = []
    tx_hashes: set[str] = set()
    candidate_incidents: set[str] = set()
    confidence_counts = Counter()
    review_status_counts = Counter()
    source_type_counts = Counter()

    for item in candidates.get("positive_candidates", []):
        incident_id = item.get("incident_id")
        if incident_id not in incident_ids:
            errors.append(f"unknown incident_id {incident_id}")
            continue
        candidate_incidents.add(incident_id)
        if item.get("chain") != incident_ids[incident_id].get("chain"):
            errors.append(f"{incident_id} chain mismatch")
        txs = item.get("candidate_transactions", [])
        if not txs:
            errors.append(f"{incident_id} has no candidate_transactions")
        for tx in txs:
            tx_hash = tx.get("tx_hash", "")
            if not TX_RE.match(tx_hash):
                errors.append(f"{incident_id} invalid tx_hash {tx_hash}")
            if tx_hash.lower() in tx_hashes:
                errors.append(f"duplicate candidate tx_hash {tx_hash}")
            tx_hashes.add(tx_hash.lower())
            if not tx.get("candidate_role"):
                errors.append(f"{incident_id} candidate missing role")
            confidence_counts[tx.get("confidence", "unknown")] += 1
            review_status_counts[tx.get("review_status", "unknown")] += 1
            refs = tx.get("source_refs", [])
            if not refs:
                errors.append(f"{incident_id} candidate {tx_hash} missing source_refs")
            for ref in refs:
                if not ref.get("title") or not ref.get("url") or not ref.get("source_type"):
                    errors.append(f"{incident_id} candidate {tx_hash} has incomplete source_ref")
                source_type_counts[ref.get("source_type", "unknown")] += 1

    missing_ethereum_candidates = sorted(ethereum_incident_ids - candidate_incidents)
    strategy = candidates.get("normal_complex_strategy", {})
    if not strategy.get("selection_rules"):
        errors.append("normal_complex_strategy missing selection_rules")
    if int(strategy.get("required_count", 0)) <= 0:
        errors.append("normal_complex_strategy required_count must be positive")
    required_normal_count = int(strategy.get("required_count", 0))
    normal_candidates = read_json_or_none(root / args.normal_candidates)
    normal_items = normal_candidates.get("items", []) if normal_candidates else []
    normal_bucket_counts = Counter()
    normal_tx_hashes: set[str] = set()
    for item in normal_items:
        tx_hash = item.get("tx_hash", "")
        if not TX_RE.match(tx_hash):
            errors.append(f"normal candidate invalid tx_hash {tx_hash}")
        if tx_hash.lower() in normal_tx_hashes:
            errors.append(f"duplicate normal candidate tx_hash {tx_hash}")
        normal_tx_hashes.add(tx_hash.lower())
        if item.get("chain") != "ethereum" or item.get("chain_id") != 1:
            errors.append(f"normal candidate {tx_hash} is not ethereum mainnet")
        if item.get("candidate_label") != 0:
            errors.append(f"normal candidate {tx_hash} candidate_label must be 0")
        if not item.get("promotion_required"):
            errors.append(f"normal candidate {tx_hash} must require promotion")
        normal_bucket_counts[item.get("selection_bucket", "unknown")] += 1
    if normal_candidates and len(normal_tx_hashes) < required_normal_count:
        errors.append(
            f"normal candidates below required_count: {len(normal_tx_hashes)} < {required_normal_count}"
        )

    normal_candidate_status = "not_seeded"
    if normal_candidates:
        normal_candidate_status = (
            "candidate_queue_seeded_pending_trace"
            if len(normal_tx_hashes) >= required_normal_count
            else "candidate_queue_incomplete"
        )

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "positive_candidate_incidents": len(candidate_incidents),
        "candidate_transactions": len(tx_hashes),
        "missing_ethereum_candidate_incidents": missing_ethereum_candidates,
        "normal_complex_strategy_status": normal_candidate_status,
        "normal_complex_strategy_plan_status": strategy.get("review_status"),
        "normal_complex_required_count": strategy.get("required_count"),
        "normal_candidate_transactions": len(normal_tx_hashes),
        "normal_candidate_bucket_counts": dict(sorted(normal_bucket_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "review_status_counts": dict(sorted(review_status_counts.items())),
        "source_type_counts": dict(sorted(source_type_counts.items())),
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
