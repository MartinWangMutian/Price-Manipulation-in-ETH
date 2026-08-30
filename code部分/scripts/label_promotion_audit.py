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
VALID_PENDING = {"pending_trace", "pending_review", "unlabeled", "rejected", "promoted"}


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
    promoted = item.get("decision") == "promoted"
    if promoted != (item.get("promotion_status") == "promoted"):
        errors.append(f"{tx_hash} decision/promotion_status mismatch")
    if promoted:
        if item.get("analyst") in {"", "TBD", None}:
            errors.append(f"{tx_hash} promoted without analyst")
        if not item.get("reviewed_at"):
            errors.append(f"{tx_hash} promoted without reviewed_at")
        if not item.get("trace_bundle_ref"):
            errors.append(f"{tx_hash} promoted without trace_bundle_ref")
        if not item.get("graph_ref"):
            errors.append(f"{tx_hash} promoted without graph_ref")
        if not item.get("label_scope"):
            errors.append(f"{tx_hash} promoted without label_scope")
        if not item.get("label_version"):
            errors.append(f"{tx_hash} promoted without label_version")
        if not item.get("incident_evidence_refs"):
            errors.append(f"{tx_hash} promoted without evidence refs")
        if expected_label == 0 and item.get("negative_screening", {}).get("status") != "pass":
            errors.append(f"{tx_hash} promoted negative without passing screening")
    return errors


def audit_stage4_refs(root: Path, item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tx_hash = str(item.get("tx_hash", "")).lower()
    for field, expected_kind in (("trace_bundle_ref", "trace"), ("graph_ref", "graph")):
        ref = item.get(field)
        if not isinstance(ref, str):
            errors.append(f"{tx_hash} missing {field}")
            continue
        path = root / ref
        if not path.is_file():
            errors.append(f"{tx_hash} dangling {field}: {ref}")
            continue
        payload = read_json(path)
        if str(payload.get("tx_hash", "")).lower() != tx_hash:
            errors.append(f"{tx_hash} {field} transaction mismatch")
        if expected_kind == "trace":
            if payload.get("trace_source") != "trace_transaction" or payload.get("trace_status") != "ok":
                errors.append(f"{tx_hash} invalid trace source/status")
            if not payload.get("calls"):
                errors.append(f"{tx_hash} empty trace bundle")
        elif not payload.get("nodes") or not payload.get("edges"):
            errors.append(f"{tx_hash} empty graph")
    if not item.get("raw_trace_sha256"):
        errors.append(f"{tx_hash} missing raw trace hash")
    if not item.get("reason_codes"):
        errors.append(f"{tx_hash} missing reason codes")
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
    stage4 = decisions.get("schema_ver") == "label-promotion-decisions.stage4.v1"
    exploit_queue_ids = queue_ids(root / args.exploit_queue)
    normal_queue_ids = queue_ids(root / args.normal_queue)
    errors: list[str] = []
    decision_counts = Counter()
    promotion_counts = Counter()
    promoted_label_counts = Counter()
    seen_queue_ids: set[str] = set()
    seen_tx_hashes: set[str] = set()

    for items, expected_label, expected_queue_ids in (
        (decisions.get("exploit_decisions", []), 1, exploit_queue_ids),
        (decisions.get("normal_decisions", []), 0, normal_queue_ids),
    ):
        actual_queue_ids = {item.get("queue_id") for item in items}
        if actual_queue_ids != expected_queue_ids:
            errors.append(
                f"label {expected_label} queue coverage mismatch: expected={len(expected_queue_ids)} "
                f"actual={len(actual_queue_ids)}"
            )
        for item in items:
            errors.extend(audit_decision(item, expected_label, expected_queue_ids))
            if stage4:
                errors.extend(audit_stage4_refs(root, item))
            queue_id = item.get("queue_id")
            tx_hash = str(item.get("tx_hash", "")).lower()
            if queue_id in seen_queue_ids:
                errors.append(f"duplicate queue_id {queue_id}")
            seen_queue_ids.add(queue_id)
            if tx_hash in seen_tx_hashes:
                errors.append(f"duplicate tx_hash {tx_hash}")
            seen_tx_hashes.add(tx_hash)
            decision_counts[item.get("decision", "unknown")] += 1
            promotion_counts[item.get("promotion_status", "unknown")] += 1
            if item.get("decision") == "promoted":
                promoted_label_counts[expected_label] += 1

    promoted = decision_counts.get("promoted", 0)
    training_ready = set(promoted_label_counts) == {0, 1} and not errors
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "training_ready": training_ready,
        "training_scope": decisions.get("training_scope"),
        "research_training_ready": decisions.get("research_training_ready", False),
        "exploit_decisions": len(decisions.get("exploit_decisions", [])),
        "normal_decisions": len(decisions.get("normal_decisions", [])),
        "decision_counts": dict(sorted(decision_counts.items())),
        "promotion_counts": dict(sorted(promotion_counts.items())),
        "promoted_markers": promoted,
        "promoted_label_counts": {
            str(key): value for key, value in sorted(promoted_label_counts.items())
        },
        "coverage": {
            "expected": len(exploit_queue_ids) + len(normal_queue_ids),
            "observed": len(seen_queue_ids),
        },
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
