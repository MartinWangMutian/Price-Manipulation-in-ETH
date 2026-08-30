#!/usr/bin/env python3
"""Build the versioned Stage 8 research expansion queues and sampling contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TX_HASH_LENGTH = 66


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_hash(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def valid_tx_hash(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != TX_HASH_LENGTH or not value.startswith("0x"):
        return False
    try:
        int(value[2:], 16)
    except ValueError:
        return False
    return True


def queue_id_for(snapshot_id: str, incident_id: str, tx_hash: str) -> str:
    seed = f"{snapshot_id}:{incident_id}:{tx_hash.lower()}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def queue_hashes(payload: dict[str, Any]) -> set[str]:
    return {
        str(item.get("tx_hash", "")).lower()
        for item in payload.get("items", [])
        if valid_tx_hash(item.get("tx_hash"))
    }


def held_out_hashes(split_manifest: dict[str, Any], split_name: str) -> set[str]:
    hashes: set[str] = set()
    for group in split_manifest.get("groups", []):
        if group.get("split") != split_name:
            continue
        hashes.update(str(value).lower() for value in group.get("tx_hashes", []))
    return hashes


def validate_incidents(config: dict[str, Any], payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    verified: list[dict[str, Any]] = []
    event_types = set(config["evidence_policy"]["qualifying_event_source_types"])
    tx_types = set(config["evidence_policy"]["required_transaction_source_types"])
    seen_ids: set[str] = set()
    seen_groups: set[str] = set()
    seen_hashes: set[str] = set()

    if payload.get("chain") != "ethereum" or payload.get("chain_id") != 1:
        errors.append("incident manifest must be Ethereum mainnet only")
    for incident in payload.get("incidents", []):
        incident_id = incident.get("incident_id")
        group = incident.get("independent_event_group")
        prefix = str(incident_id or "missing_incident")
        if not isinstance(incident_id, str) or not incident_id:
            errors.append("incident missing incident_id")
            continue
        if incident_id in seen_ids:
            errors.append(f"{prefix}: duplicate incident_id")
        seen_ids.add(incident_id)
        if not isinstance(group, str) or not group:
            errors.append(f"{prefix}: missing independent_event_group")
        elif group in seen_groups:
            errors.append(f"{prefix}: duplicate independent_event_group {group}")
        else:
            seen_groups.add(group)

        anchors = incident.get("anchor_transactions", [])
        if not isinstance(anchors, list) or not anchors:
            errors.append(f"{prefix}: at least one anchor transaction is required")
            anchors = []
        for tx_hash in anchors:
            if not valid_tx_hash(tx_hash):
                errors.append(f"{prefix}: invalid transaction hash {tx_hash}")
                continue
            lowered = tx_hash.lower()
            if lowered in seen_hashes:
                errors.append(f"{prefix}: duplicate anchor transaction {lowered}")
            seen_hashes.add(lowered)

        event_evidence_types = {
            item.get("source_type") for item in incident.get("event_evidence", []) if isinstance(item, dict)
        }
        transaction_evidence_types = {
            item.get("source_type")
            for item in incident.get("transaction_evidence", [])
            if isinstance(item, dict)
        }
        urls = [
            item.get("url")
            for field in ("event_evidence", "transaction_evidence")
            for item in incident.get(field, [])
            if isinstance(item, dict)
        ]
        if any(not isinstance(url, str) or not url.startswith("https://") for url in urls):
            errors.append(f"{prefix}: evidence URLs must use https")

        if incident.get("status") == "verified_anchor":
            if not (event_evidence_types & event_types):
                errors.append(f"{prefix}: no qualifying event evidence")
            missing_tx_types = sorted(tx_types - transaction_evidence_types)
            if missing_tx_types:
                errors.append(f"{prefix}: missing transaction evidence types {missing_tx_types}")
            verified.append(incident)
        elif incident.get("status") not in set(config["evidence_policy"]["review_hold_statuses"]):
            errors.append(f"{prefix}: invalid status {incident.get('status')}")
    return verified, errors


def build_positive_item(
    snapshot_id: str, incident: dict[str, Any], tx_hash: str
) -> dict[str, Any]:
    return {
        "queue_id": queue_id_for(snapshot_id, incident["incident_id"], tx_hash),
        "incident_id": incident["incident_id"],
        "independent_event_group": incident["independent_event_group"],
        "chain": "ethereum",
        "chain_id": 1,
        "tx_hash": tx_hash.lower(),
        "candidate_role": "research_attack_anchor",
        "confidence": "high",
        "review_status": "needs_paid_trace_graph_and_human_promotion",
        "preferred_rpc_methods": ["trace_transaction"],
        "promotion_required": True,
        "event_evidence": incident["event_evidence"],
        "transaction_evidence": incident["transaction_evidence"],
    }


def promoted_counts(label_snapshot: dict[str, Any]) -> dict[str, int]:
    counts = {"positive": 0, "negative": 0, "unlabeled": 0}
    stored_counts = label_snapshot.get("label_counts")
    if isinstance(stored_counts, dict):
        counts["positive"] = int(stored_counts.get("1", 0))
        counts["negative"] = int(stored_counts.get("0", 0))
        counts["unlabeled"] = int(label_snapshot.get("decision_counts", {}).get("unlabeled", 0))
        return counts
    for item in label_snapshot.get("items", []):
        label = item.get("label")
        if label == 1:
            counts["positive"] += 1
        elif label == 0:
            counts["negative"] += 1
        else:
            counts["unlabeled"] += 1
    return counts


def build_outputs(
    config: dict[str, Any],
    incidents_payload: dict[str, Any],
    existing_queue: dict[str, Any],
    split_manifest: dict[str, Any],
    label_snapshot: dict[str, Any],
) -> dict[str, Any]:
    verified, errors = validate_incidents(config, incidents_payload)
    targets = config["targets"]
    snapshot_id = config["snapshot_id"]
    verified_groups = {item["independent_event_group"] for item in verified}
    if len(verified_groups) < targets["independent_attack_events"]:
        errors.append(
            "verified independent event target not met: "
            f"{len(verified_groups)}/{targets['independent_attack_events']}"
        )

    split_name = config["split_policy"]["held_out_split"]
    frozen_hashes = held_out_hashes(split_manifest, split_name)
    existing_hashes = queue_hashes(existing_queue)
    verified_anchor_hashes = {
        str(tx_hash).lower()
        for incident in verified
        for tx_hash in incident.get("anchor_transactions", [])
    }
    existing_frozen_anchors = sorted(verified_anchor_hashes & frozen_hashes & existing_hashes)
    overlap = sorted((verified_anchor_hashes - existing_hashes) & frozen_hashes)
    if overlap:
        errors.append(f"new verified anchors overlap frozen held-out transactions: {overlap}")

    all_items = [
        build_positive_item(snapshot_id, incident, tx_hash)
        for incident in verified
        for tx_hash in incident["anchor_transactions"]
        if str(tx_hash).lower() not in existing_hashes
    ]
    all_items.sort(key=lambda item: (item["incident_id"], item["tx_hash"]))
    pilot_incident = config["pilot"]["incident_id"]
    pilot_items = [item for item in all_items if item["incident_id"] == pilot_incident]
    expected_pilot = config["paid_call_guards"]["pilot_positive_count"]
    if len(pilot_items) != expected_pilot:
        errors.append(
            f"pilot positive queue must contain {expected_pilot} item(s), found {len(pilot_items)}"
        )

    created_at = now_iso()
    promotion_criteria = [
        "trace_transaction succeeds on Ethereum mainnet with a non-empty trace",
        "transaction, receipt, and block hashes agree",
        "rich graph passes structural quality gates",
        "analyst confirms event role and promotes a new versioned label",
    ]
    queue_base = {
        "schema_ver": config["versions"]["queue_schema"],
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "trace_method": "trace_transaction",
        "promotion_criteria": promotion_criteria,
        "skipped": [],
    }
    positive_queue = {**queue_base, "items": all_items}
    pilot_queue = {**queue_base, "snapshot_id": f"{snapshot_id}.positive-pilot", "items": pilot_items}

    target_per_event = config["negative_sampling"]["target_per_event"]
    negative_requests = []
    for incident in sorted(verified, key=lambda item: item["incident_id"]):
        negative_requests.append(
            {
                "request_id": hashlib.sha256(
                    f"{snapshot_id}:negative:{incident['incident_id']}".encode("utf-8")
                ).hexdigest(),
                "incident_id": incident["incident_id"],
                "independent_event_group": incident["independent_event_group"],
                "affected_protocol": incident["affected_protocol"],
                "anchor_transactions": [value.lower() for value in incident["anchor_transactions"]],
                "requested_candidates": target_per_event,
                "incident_exclusion_window_blocks": config["negative_sampling"][
                    "incident_exclusion_window_blocks"
                ],
                "matching_dimensions": config["negative_sampling"]["matching_dimensions"],
                "candidate_label": None,
                "review_status": "needs_metadata_sampling_trace_and_human_screening",
            }
        )
    negative_plan = {
        "schema_ver": "research-negative-sampling-plan.stage8.v1",
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "requested_total": sum(item["requested_candidates"] for item in negative_requests),
        "held_out_exclusions_sha256": canonical_hash(sorted(frozen_hashes)),
        "frozen_held_out_count": len(frozen_hashes),
        "requests": negative_requests,
    }

    label_counts = promoted_counts(label_snapshot)
    progress = {
        "verified_independent_events": len(verified_groups),
        "verified_anchor_transactions": len(verified_anchor_hashes),
        "current_promoted_positive_rich_graphs": label_counts["positive"],
        "current_promoted_negative_rich_graphs": label_counts["negative"],
        "positive_rich_graph_gap": max(0, targets["positive_rich_graphs"] - label_counts["positive"]),
        "negative_rich_graph_gap": max(0, targets["negative_rich_graphs"] - label_counts["negative"]),
        "new_positive_anchor_queue_items": len(all_items),
        "negative_sampling_slots": negative_plan["requested_total"],
    }
    complete = (
        progress["verified_independent_events"] >= targets["independent_attack_events"]
        and progress["current_promoted_positive_rich_graphs"] >= targets["positive_rich_graphs"]
        and progress["current_promoted_negative_rich_graphs"] >= targets["negative_rich_graphs"]
    )
    status = "failed" if errors else ("complete" if complete else "ready_for_pilot")
    index = {
        "schema_ver": "research-expansion-index.stage8.v1",
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "status": status,
        "research_target_complete": complete,
        "progress": progress,
        "lineage": {
            "incident_manifest_sha256": canonical_hash(incidents_payload),
            "frozen_split_content_hash": split_manifest.get("split_content_hash"),
            "frozen_split_sha256": canonical_hash(split_manifest),
            "label_content_hash": label_snapshot.get("label_content_hash"),
            "label_snapshot_sha256": canonical_hash(label_snapshot),
            "feature_version": config["versions"]["feature_version"],
        },
        "review_hold_incidents": [
            {
                "incident_id": item["incident_id"],
                "reason": item.get("hold_reason"),
            }
            for item in incidents_payload.get("incidents", [])
            if item.get("status") != "verified_anchor"
        ],
        "frozen_held_out_count": len(frozen_hashes),
        "frozen_held_out_hashes_sha256": canonical_hash(sorted(frozen_hashes)),
        "existing_frozen_anchor_count": len(existing_frozen_anchors),
        "errors": errors,
    }
    report = {
        "checked_at": created_at,
        "gate": "stage8_research_expansion_builder",
        "status": status,
        "research_target_complete": complete,
        "progress": progress,
        "verified_event_target_met": progress["verified_independent_events"]
        >= targets["independent_attack_events"],
        "positive_graph_target_met": progress["current_promoted_positive_rich_graphs"]
        >= targets["positive_rich_graphs"],
        "negative_graph_target_met": progress["current_promoted_negative_rich_graphs"]
        >= targets["negative_rich_graphs"],
        "new_frozen_held_out_overlap": overlap,
        "existing_frozen_anchor_count": len(existing_frozen_anchors),
        "paid_calls_performed": 0,
        "next_gate": "one verified positive anchor plus five unlabeled matched negative candidates",
        "errors": errors,
    }
    return {
        "positive_queue": positive_queue,
        "pilot_queue": pilot_queue,
        "negative_plan": negative_plan,
        "index": index,
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Stage 8 research expansion artifacts.")
    parser.add_argument("--config", default="config/research_expansion.stage8.v1.json")
    parser.add_argument("--incidents", default="data/training/research_incidents.stage8.v1.json")
    parser.add_argument("--existing-positive-queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--split-manifest", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--label-snapshot", default="data/training/label_snapshot.stage4.v1.json")
    parser.add_argument("--positive-queue-out", default="data/training/research_positive_trace_queue.stage8.v1.json")
    parser.add_argument("--pilot-positive-queue-out", default="data/training/research_pilot_positive_trace_queue.stage8.v1.json")
    parser.add_argument("--negative-plan-out", default="data/training/research_negative_sampling_plan.stage8.v1.json")
    parser.add_argument("--index-out", default="data/training/research_expansion_index.stage8.v1.json")
    parser.add_argument("--report", default="ops/reports/research-expansion-builder.stage8.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    outputs = build_outputs(
        read_json(root / args.config),
        read_json(root / args.incidents),
        read_json(root / args.existing_positive_queue),
        read_json(root / args.split_manifest),
        read_json(root / args.label_snapshot),
    )
    write_json(root / args.positive_queue_out, outputs["positive_queue"])
    write_json(root / args.pilot_positive_queue_out, outputs["pilot_queue"])
    write_json(root / args.negative_plan_out, outputs["negative_plan"])
    write_json(root / args.index_out, outputs["index"])
    write_json(root / args.report, outputs["report"])
    print(json.dumps(outputs["report"], indent=2, sort_keys=True))
    return 0 if outputs["report"]["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
