#!/usr/bin/env python3
"""Audit Stage 4 labels and grouped splits for dangling refs and leakage."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grouped_split_builder import canonical_hash, related_negative_pairs, sha256_file, target_counts


SPLIT_ORDER = ("train", "validation", "held_out_test")


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Stage 4 grouped split manifest.")
    parser.add_argument("--policy", default="config/label_review_policy.stage4.v1.json")
    parser.add_argument("--decisions", default="data/training/label_promotion_decisions.stage4.v1.json")
    parser.add_argument("--labels", default="data/training/graph_labels.stage4.v1.json")
    parser.add_argument("--manifest", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--snapshot", default="data/training/label_snapshot.stage4.v1.json")
    parser.add_argument("--split-dir", default="data/training/splits/stage4")
    parser.add_argument("--normal-queue", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--out", default="ops/reports/split-manifest-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    policy = read_json(root / args.policy)
    decisions = read_json(root / args.decisions)
    labels_payload = read_json(root / args.labels)
    manifest = read_json(root / args.manifest)
    snapshot = read_json(root / args.snapshot)
    normal_items = read_json(root / args.normal_queue).get("items", [])
    errors: list[str] = []

    decision_items = [
        item
        for key in ("exploit_decisions", "normal_decisions")
        for item in decisions.get(key, [])
    ]
    promoted = {item["tx_hash"].lower(): item for item in decision_items if item.get("decision") == "promoted"}
    labels = labels_payload.get("labels", [])
    labels_by_tx = {item["tx_hash"].lower(): item for item in labels}
    items = manifest.get("items", [])
    items_by_tx = {item["tx_hash"].lower(): item for item in items}
    if len(labels_by_tx) != len(labels):
        errors.append("duplicate transaction in graph labels")
    if len(items_by_tx) != len(items):
        errors.append("duplicate transaction in split manifest")
    if set(promoted) != set(labels_by_tx):
        errors.append("promoted decisions do not exactly match graph labels")
    if set(labels_by_tx) != set(items_by_tx):
        errors.append("graph labels do not exactly match split items")

    expected_decision_hash = canonical_hash(
        {
            "exploit_decisions": decisions.get("exploit_decisions", []),
            "normal_decisions": decisions.get("normal_decisions", []),
        }
    )
    if decisions.get("decision_content_hash") != expected_decision_hash:
        errors.append("decision content hash mismatch")
    if labels_payload.get("label_content_hash") != canonical_hash(labels):
        errors.append("label content hash mismatch")
    if manifest.get("split_content_hash") != canonical_hash(items):
        errors.append("split content hash mismatch")

    feature_versions = set()
    for tx_hash, item in items_by_tx.items():
        graph_ref = root / item["graph_ref"]
        if not graph_ref.exists():
            errors.append(f"missing graph ref {item['graph_ref']}")
            continue
        if sha256_file(graph_ref) != item.get("graph_sha256"):
            errors.append(f"graph hash mismatch {tx_hash}")
        graph = read_json(graph_ref)
        if graph.get("tx_hash", "").lower() != tx_hash:
            errors.append(f"graph transaction mismatch {tx_hash}")
        if graph.get("graph_id") != item.get("graph_id"):
            errors.append(f"graph id mismatch {tx_hash}")
        feature_versions.add(item.get("feature_version"))
        if item.get("label") != labels_by_tx.get(tx_hash, {}).get("label"):
            errors.append(f"label mismatch {tx_hash}")
    expected_graph_data_hash = canonical_hash(
        sorted((item["tx_hash"], item["graph_sha256"]) for item in items)
    )
    if manifest.get("graph_data_hash") != expected_graph_data_hash:
        errors.append("graph data hash mismatch")
    if feature_versions != {policy["feature_version"]}:
        errors.append(f"feature version mismatch: {sorted(str(value) for value in feature_versions)}")

    group_splits: dict[str, set[str]] = {}
    for item in items:
        group_splits.setdefault(item["group_id"], set()).add(item["split"])
    leaked_groups = sorted(group_id for group_id, splits in group_splits.items() if len(splits) != 1)
    if leaked_groups:
        errors.append(f"groups cross splits: {leaked_groups}")

    positive_incident_splits: dict[str, set[str]] = {}
    for item in items:
        if item["label"] == 1:
            positive_incident_splits.setdefault(item["incident_id"], set()).add(item["split"])
    leaked_incidents = sorted(key for key, splits in positive_incident_splits.items() if len(splits) != 1)
    if leaked_incidents:
        errors.append(f"positive incidents cross splits: {leaked_incidents}")

    observed_at_by_tx = {item["tx_hash"].lower(): item.get("observed_at") for item in decision_items}
    split_policy = policy["split_policy"]
    promoted_normal = [item for item in normal_items if item["tx_hash"].lower() in items_by_tx]
    related_addresses_by_tx = {}
    for tx_hash, item in items_by_tx.items():
        graph = read_json(root / item["graph_ref"])
        related_addresses_by_tx[tx_hash] = {
            str(node["address"]).lower()
            for node in graph.get("nodes", [])
            if node.get("address")
        }
    relations = related_negative_pairs(
        promoted_normal,
        observed_at_by_tx,
        int(split_policy["temporal_window_seconds"]),
        int(split_policy["max_shared_endpoint_frequency"]),
        related_addresses_by_tx,
    )
    relation_leaks = []
    for left, right, shared in relations:
        left_item = items_by_tx[left]
        right_item = items_by_tx[right]
        if left_item["group_id"] != right_item["group_id"] or left_item["split"] != right_item["split"]:
            relation_leaks.append({"left": left, "right": right, "shared_endpoints": shared})
    if relation_leaks:
        errors.append(f"related negative pairs cross groups/splits: {len(relation_leaks)}")

    label_counts = Counter(item["label"] for item in items)
    split_counts = Counter(item["split"] for item in items)
    split_label_counts = {
        split: Counter(item["label"] for item in items if item["split"] == split)
        for split in SPLIT_ORDER
    }
    if set(split_counts) != set(SPLIT_ORDER):
        errors.append("missing required split")
    for split, counts in split_label_counts.items():
        if set(counts) != {0, 1}:
            errors.append(f"split {split} does not contain both labels")
    targets = {
        str(label): target_counts(label_counts[label], split_policy["ratios"])
        for label in (0, 1)
    }
    for split in SPLIT_ORDER:
        for label in (0, 1):
            if split_label_counts[split][label] != targets[str(label)][split]:
                errors.append(
                    f"split target mismatch split={split} label={label} "
                    f"expected={targets[str(label)][split]} actual={split_label_counts[split][label]}"
                )
    if manifest.get("frozen") is not True:
        errors.append("split manifest is not frozen")
    if not manifest.get("held_out_test_policy"):
        errors.append("held-out test usage policy missing")
    for split in SPLIT_ORDER:
        split_path = root / args.split_dir / f"{split}.v1.json"
        if not split_path.is_file():
            errors.append(f"missing split file {split_path}")
            continue
        split_payload = read_json(split_path)
        expected_items = [item for item in items if item["split"] == split]
        if split_payload.get("items") != expected_items:
            errors.append(f"split file items mismatch: {split}")
        if split_payload.get("split_content_hash") != canonical_hash(expected_items):
            errors.append(f"split file content hash mismatch: {split}")
        if split == "held_out_test" and split_payload.get("frozen") is not True:
            errors.append("held-out split file is not frozen")
    if snapshot.get("engineering_smoke_training_ready") is not True:
        errors.append("engineering smoke snapshot is not training-ready")
    if snapshot.get("research_training_ready") is not False:
        errors.append("small Stage 4 snapshot must not be research-ready")
    for field, expected in (
        ("decision_content_hash", decisions.get("decision_content_hash")),
        ("label_content_hash", labels_payload.get("label_content_hash")),
        ("split_content_hash", manifest.get("split_content_hash")),
        ("graph_data_hash", manifest.get("graph_data_hash")),
    ):
        if snapshot.get(field) != expected:
            errors.append(f"snapshot {field} mismatch")

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "transactions": len(items),
        "label_counts": {str(key): value for key, value in sorted(label_counts.items())},
        "split_counts": dict(sorted(split_counts.items())),
        "split_label_counts": {
            split: {str(key): value for key, value in sorted(counts.items())}
            for split, counts in split_label_counts.items()
        },
        "groups": len(group_splits),
        "related_negative_pairs_checked": len(relations),
        "group_leaks": leaked_groups,
        "incident_leaks": leaked_incidents,
        "relation_leaks": relation_leaks,
        "held_out_test_frozen": manifest.get("frozen") is True,
        "engineering_smoke_training_ready": not errors,
        "research_training_ready": False,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
