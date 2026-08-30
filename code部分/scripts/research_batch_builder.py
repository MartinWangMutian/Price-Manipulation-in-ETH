#!/usr/bin/env python3
"""Build and validate a bounded Stage 8 paid research batch."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_expansion_builder import (
    canonical_hash,
    held_out_hashes,
    read_json,
    valid_tx_hash,
    write_json,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def build_batch(
    config: dict[str, Any],
    full_positive: dict[str, Any],
    split: dict[str, Any],
    negative_queues: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    incident_ids = list(config.get("positive_incident_ids", []))
    if len(incident_ids) != len(set(incident_ids)):
        errors.append("positive incident IDs are not unique")
    if len(incident_ids) != int(config.get("positive_count", -1)):
        errors.append("positive incident count differs from positive_count")
    if config.get("trace_method") != "trace_transaction":
        errors.append("batch trace method must be trace_transaction")
    guards = config.get("paid_call_guards", {})
    if not guards.get("forbid_debug_trace_transaction"):
        errors.append("debug_traceTransaction must be forbidden")
    if not guards.get("stop_after_batch"):
        errors.append("stop_after_batch must be enabled")
    if config.get("label_policy", {}).get("automatic_label_promotion") is not False:
        errors.append("automatic label promotion must be false")

    by_incident: dict[str, list[dict[str, Any]]] = {}
    for item in full_positive.get("items", []):
        by_incident.setdefault(str(item.get("incident_id")), []).append(item)
    positive_items: list[dict[str, Any]] = []
    for incident_id in incident_ids:
        matches = by_incident.get(incident_id, [])
        if len(matches) != 1:
            errors.append(f"expected one positive anchor for {incident_id}, found {len(matches)}")
            continue
        positive_items.append(matches[0])

    frozen = held_out_hashes(split, "held_out_test")
    positive_hashes = {str(item.get("tx_hash", "")).lower() for item in positive_items}
    if len(positive_hashes) != len(positive_items):
        errors.append("positive batch contains duplicate transaction hashes")
    overlap = sorted(positive_hashes & frozen)
    if overlap:
        errors.append(f"positive batch overlaps frozen held-out hashes: {overlap}")

    negative_items = [
        item for queue in negative_queues for item in queue.get("items", [])
    ]
    negative_hashes = {str(item.get("tx_hash", "")).lower() for item in negative_items}
    if len(negative_hashes) != len(negative_items):
        errors.append("negative batch contains duplicate transaction hashes")
    if any(not valid_tx_hash(item.get("tx_hash")) for item in negative_items):
        errors.append("negative batch contains invalid transaction hashes")
    if any(item.get("candidate_label") is not None for item in negative_items):
        errors.append("negative candidates must remain unlabeled")
    if any(item.get("preferred_rpc_methods") != ["trace_transaction"] for item in negative_items):
        errors.append("negative candidates allow an unapproved trace method")
    negative_positive_overlap = sorted(negative_hashes & positive_hashes)
    if negative_positive_overlap:
        errors.append(f"negative candidates overlap positive anchors: {negative_positive_overlap}")
    negative_frozen_overlap = sorted(negative_hashes & frozen)
    if negative_frozen_overlap:
        errors.append(f"negative candidates overlap frozen held-out hashes: {negative_frozen_overlap}")

    expected_per_incident = int(config.get("negative_per_incident", 0))
    counts = Counter(str(item.get("matched_incident_id")) for item in negative_items)
    if negative_queues:
        for incident_id in incident_ids:
            if counts[incident_id] != expected_per_incident:
                errors.append(
                    f"negative count for {incident_id} is {counts[incident_id]}, "
                    f"expected {expected_per_incident}"
                )
        unexpected = sorted(set(counts) - set(incident_ids))
        if unexpected:
            errors.append(f"negative batch contains unexpected incident groups: {unexpected}")
        if len(negative_items) != int(config.get("negative_count", -1)):
            errors.append("negative batch total differs from negative_count")

    expected_total = int(config.get("positive_count", 0)) + int(config.get("negative_count", 0))
    if expected_total > int(config.get("max_paid_trace_calls", 0)):
        errors.append("configured batch exceeds max_paid_trace_calls")

    created_at = now_iso()
    base_queue = {
        "schema_ver": "trace-replay-queue.v1",
        "snapshot_id": config.get("batch_id"),
        "created_at": created_at,
        "trace_method": "trace_transaction",
        "skipped": [],
    }
    positive_queue = {
        **base_queue,
        "snapshot_id": f"{config.get('batch_id')}.positive",
        "promotion_criteria": [
            "trace_transaction and rich graph pass every structural gate",
            "event evidence and graph are human-reviewed before label promotion",
        ],
        "items": positive_items,
    }
    negative_queue = {
        **base_queue,
        "snapshot_id": f"{config.get('batch_id')}.negative",
        "promotion_criteria": [
            "trace_transaction and rich graph pass every structural gate",
            "external screening and analyst review confirm legitimate behavior",
            "ambiguous candidates remain unlabeled",
        ],
        "items": negative_items,
    }
    ready = bool(negative_queues) and not errors
    report = {
        "checked_at": created_at,
        "gate": "stage8_research_batch_builder",
        "batch_id": config.get("batch_id"),
        "status": "ready_for_paid_dry_run" if ready else (
            "ready_for_negative_sampling" if not errors else "failed"
        ),
        "positive_count": len(positive_items),
        "negative_count": len(negative_items),
        "negative_counts_by_incident": dict(sorted(counts.items())),
        "max_paid_trace_calls": config.get("max_paid_trace_calls"),
        "trace_method": config.get("trace_method"),
        "labels_promoted": 0,
        "frozen_held_out_overlap": sorted((positive_hashes | negative_hashes) & frozen),
        "positive_queue_sha256": canonical_hash(positive_queue),
        "negative_queue_sha256": canonical_hash(negative_queue),
        "errors": errors,
    }
    return {"positive_queue": positive_queue, "negative_queue": negative_queue, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded Stage 8 research batch.")
    parser.add_argument("--config", default="config/research_batch.stage8.round-002.v1.json")
    parser.add_argument(
        "--full-positive", default="data/training/research_positive_trace_queue.stage8.v1.json"
    )
    parser.add_argument("--split", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--negative-queue", action="append", default=[])
    parser.add_argument(
        "--positive-out", default="data/training/research_positive_trace_queue.stage8.round-002.v1.json"
    )
    parser.add_argument(
        "--negative-out", default="data/training/research_negative_trace_queue.stage8.round-002.v1.json"
    )
    parser.add_argument(
        "--report", default="ops/reports/research-batch-builder.stage8.round-002.latest.json"
    )
    args = parser.parse_args()

    root = Path.cwd()
    outputs = build_batch(
        read_json(root / args.config),
        read_json(root / args.full_positive),
        read_json(root / args.split),
        [read_json(root / path) for path in args.negative_queue],
    )
    write_json(root / args.positive_out, outputs["positive_queue"])
    write_json(root / args.negative_out, outputs["negative_queue"])
    write_json(root / args.report, outputs["report"])
    print(json.dumps(outputs["report"], indent=2, sort_keys=True))
    return 0 if outputs["report"]["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
