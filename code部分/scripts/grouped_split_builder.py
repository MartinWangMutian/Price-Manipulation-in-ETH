#!/usr/bin/env python3
"""Build deterministic, leakage-aware Stage 4 graph splits."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_rank(seed: int, *parts: str) -> str:
    return hashlib.sha256(":".join([str(seed), *parts]).encode("utf-8")).hexdigest()


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def target_counts(total: int, ratios: dict[str, float]) -> dict[str, int]:
    raw = {name: total * float(ratios[name]) for name in SPLIT_ORDER}
    counts = {name: int(raw[name]) for name in SPLIT_ORDER}
    remainder = total - sum(counts.values())
    order = sorted(SPLIT_ORDER, key=lambda name: (-(raw[name] - counts[name]), SPLIT_ORDER.index(name)))
    for name in order[:remainder]:
        counts[name] += 1
    return counts


class UnionFind:
    def __init__(self, values: list[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def related_negative_pairs(
    normal_items: list[dict[str, Any]],
    observed_at_by_tx: dict[str, str],
    window_seconds: int,
    max_shared_endpoint_frequency: int,
    related_addresses_by_tx: dict[str, set[str]] | None = None,
) -> list[tuple[str, str, list[str]]]:
    address_sets: dict[str, set[str]] = {}
    for item in normal_items:
        tx_hash = item["tx_hash"].lower()
        addresses = {
            value.lower()
            for value in (item.get("from"), item.get("to"))
            if isinstance(value, str)
        }
        if related_addresses_by_tx:
            addresses.update(related_addresses_by_tx.get(tx_hash, set()))
        address_sets[tx_hash] = addresses
    endpoint_frequency = Counter(address for addresses in address_sets.values() for address in addresses)
    pairs: list[tuple[str, str, list[str]]] = []
    for index, left in enumerate(normal_items):
        left_tx = left["tx_hash"].lower()
        left_time = parse_timestamp(observed_at_by_tx.get(left_tx))
        left_endpoints = address_sets[left_tx]
        for right in normal_items[:index]:
            right_tx = right["tx_hash"].lower()
            right_time = parse_timestamp(observed_at_by_tx.get(right_tx))
            if left_time is None or right_time is None:
                continue
            if abs((left_time - right_time).total_seconds()) > window_seconds:
                continue
            right_endpoints = address_sets[right_tx]
            shared = sorted(
                endpoint
                for endpoint in left_endpoints & right_endpoints
                if endpoint_frequency[endpoint] <= max_shared_endpoint_frequency
            )
            if shared:
                pairs.append((left_tx, right_tx, shared))
    return pairs


def build_groups(
    labels: list[dict[str, Any]],
    normal_items: list[dict[str, Any]],
    observed_at_by_tx: dict[str, str],
    split_policy: dict[str, Any],
    related_addresses_by_tx: dict[str, set[str]] | None = None,
) -> dict[str, dict[str, Any]]:
    labels_by_tx = {item["tx_hash"].lower(): item for item in labels}
    groups: dict[str, dict[str, Any]] = {}
    for label in labels:
        if label["label"] != 1:
            continue
        group_id = f"incident:{label['incident_id']}"
        group = groups.setdefault(
            group_id,
            {"group_id": group_id, "label": 1, "group_type": "attack_incident", "tx_hashes": []},
        )
        group["tx_hashes"].append(label["tx_hash"].lower())

    promoted_normal = [item for item in normal_items if item["tx_hash"].lower() in labels_by_tx]
    normal_tx_hashes = [item["tx_hash"].lower() for item in promoted_normal]
    union_find = UnionFind(normal_tx_hashes)
    relations = related_negative_pairs(
        promoted_normal,
        observed_at_by_tx,
        int(split_policy["temporal_window_seconds"]),
        int(split_policy["max_shared_endpoint_frequency"]),
        related_addresses_by_tx,
    )
    for left, right, _ in relations:
        union_find.union(left, right)

    components: dict[str, list[str]] = {}
    for tx_hash in normal_tx_hashes:
        components.setdefault(union_find.find(tx_hash), []).append(tx_hash)
    for tx_hashes in components.values():
        tx_hashes = sorted(tx_hashes)
        component_hash = canonical_hash(tx_hashes)[:16]
        group_id = f"normal-temporal-address:{component_hash}"
        groups[group_id] = {
            "group_id": group_id,
            "label": 0,
            "group_type": "temporal_related_address_component",
            "tx_hashes": tx_hashes,
        }
    return groups


def assign_groups(
    groups: dict[str, dict[str, Any]], ratios: dict[str, float], seed: int
) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    assignments: dict[str, str] = {}
    targets_by_label: dict[str, dict[str, int]] = {}
    for label in (1, 0):
        label_groups = [group for group in groups.values() if group["label"] == label]
        total = sum(len(group["tx_hashes"]) for group in label_groups)
        targets = target_counts(total, ratios)
        targets_by_label[str(label)] = targets
        counts = {name: 0 for name in SPLIT_ORDER}
        label_groups.sort(key=lambda group: (-len(group["tx_hashes"]), stable_rank(seed, group["group_id"])))
        for group in label_groups:
            size = len(group["tx_hashes"])
            fitting = [name for name in SPLIT_ORDER if targets[name] - counts[name] >= size]
            if fitting:
                selected = max(
                    fitting,
                    key=lambda name: (
                        targets[name] - counts[name],
                        stable_rank(seed, group["group_id"], name),
                    ),
                )
            else:
                selected = min(
                    SPLIT_ORDER,
                    key=lambda name: (
                        abs((counts[name] + size) - targets[name]),
                        counts[name] - targets[name],
                        stable_rank(seed, group["group_id"], name),
                    ),
                )
            assignments[group["group_id"]] = selected
            counts[selected] += size
    return assignments, targets_by_label


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Stage 4 grouped splits.")
    parser.add_argument("--policy", default="config/label_review_policy.stage4.v1.json")
    parser.add_argument("--labels", default="data/training/graph_labels.stage4.v1.json")
    parser.add_argument("--decisions", default="data/training/label_promotion_decisions.stage4.v1.json")
    parser.add_argument("--normal-queue", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--out", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--split-dir", default="data/training/splits/stage4")
    parser.add_argument("--snapshot", default="data/training/label_snapshot.stage4.v1.json")
    parser.add_argument("--report", default="ops/reports/grouped-split-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    policy = read_json(root / args.policy)
    labels_payload = read_json(root / args.labels)
    decisions = read_json(root / args.decisions)
    labels = labels_payload.get("labels", [])
    normal_items = read_json(root / args.normal_queue).get("items", [])
    observed_at_by_tx = {
        item["tx_hash"].lower(): item.get("observed_at")
        for key in ("exploit_decisions", "normal_decisions")
        for item in decisions.get(key, [])
    }
    split_policy = policy["split_policy"]
    ratios = split_policy["ratios"]
    seed = int(split_policy["seed"])
    related_addresses_by_tx = {}
    for label in labels:
        graph = read_json(root / label["graph_ref"])
        related_addresses_by_tx[label["tx_hash"].lower()] = {
            str(node["address"]).lower()
            for node in graph.get("nodes", [])
            if node.get("address")
        }
    groups = build_groups(
        labels,
        normal_items,
        observed_at_by_tx,
        split_policy,
        related_addresses_by_tx,
    )
    assignments, targets_by_label = assign_groups(groups, ratios, seed)
    group_by_tx = {
        tx_hash: group
        for group in groups.values()
        for tx_hash in group["tx_hashes"]
    }

    items: list[dict[str, Any]] = []
    for label in labels:
        tx_hash = label["tx_hash"].lower()
        group = group_by_tx[tx_hash]
        graph_ref = root / label["graph_ref"]
        items.append(
            {
                "tx_hash": tx_hash,
                "graph_id": label.get("graph_id"),
                "graph_event_id": label.get("graph_event_id"),
                "graph_ref": label["graph_ref"],
                "graph_sha256": sha256_file(graph_ref),
                "label": label["label"],
                "label_semantics": label.get("label_semantics"),
                "incident_id": label.get("incident_id"),
                "group_id": group["group_id"],
                "group_type": group["group_type"],
                "split": assignments[group["group_id"]],
                "label_version": labels_payload["label_version"],
                "feature_version": label.get("feature_ver"),
            }
        )
    items.sort(key=lambda item: (SPLIT_ORDER.index(item["split"]), item["tx_hash"]))

    split_counts = Counter(item["split"] for item in items)
    split_label_counts = {
        split: {
            str(label): sum(item["split"] == split and item["label"] == label for item in items)
            for label in (0, 1)
        }
        for split in SPLIT_ORDER
    }
    graph_data_hash = canonical_hash(
        sorted((item["tx_hash"], item["graph_sha256"]) for item in items)
    )
    manifest = {
        "schema_ver": "grouped-split-manifest.stage4.v1",
        "created_at": now_iso(),
        "snapshot_id": policy["snapshot_id"],
        "label_version": labels_payload["label_version"],
        "feature_version": policy["feature_version"],
        "seed": seed,
        "ratios": ratios,
        "grouping_policy": {
            "positive": split_policy["positive_grouping"],
            "negative": split_policy["negative_grouping"],
            "temporal_window_seconds": split_policy["temporal_window_seconds"],
            "max_shared_endpoint_frequency": split_policy["max_shared_endpoint_frequency"],
        },
        "frozen": True,
        "held_out_test_policy": split_policy["test_usage_policy"],
        "training_scope": labels_payload.get("training_scope"),
        "research_training_ready": False,
        "label_content_hash": labels_payload["label_content_hash"],
        "decision_content_hash": decisions["decision_content_hash"],
        "graph_data_hash": graph_data_hash,
        "targets_by_label": targets_by_label,
        "split_counts": dict(sorted(split_counts.items())),
        "split_label_counts": split_label_counts,
        "groups": [
            {**group, "split": assignments[group_id]}
            for group_id, group in sorted(groups.items())
        ],
        "items": items,
    }
    manifest["split_content_hash"] = canonical_hash(items)
    write_json(root / args.out, manifest)

    split_dir = root / args.split_dir
    for split in SPLIT_ORDER:
        split_items = [item for item in items if item["split"] == split]
        write_json(
            split_dir / f"{split}.v1.json",
            {
                "schema_ver": "grouped-training-split.stage4.v1",
                "snapshot_id": policy["snapshot_id"],
                "split": split,
                "frozen": split == "held_out_test",
                "label_version": labels_payload["label_version"],
                "feature_version": policy["feature_version"],
                "seed": seed,
                "split_content_hash": canonical_hash(split_items),
                "items": split_items,
            },
        )

    decision_counts = Counter(
        item["decision"]
        for key in ("exploit_decisions", "normal_decisions")
        for item in decisions.get(key, [])
    )
    label_counts = Counter(str(item["label"]) for item in items)
    snapshot = {
        "schema_ver": "label-snapshot.stage4.v1",
        "created_at": now_iso(),
        "snapshot_id": policy["snapshot_id"],
        "label_version": labels_payload["label_version"],
        "feature_version": policy["feature_version"],
        "training_scope": "engineering_smoke_only",
        "decision_counts": dict(sorted(decision_counts.items())),
        "promoted_labels": len(items),
        "label_counts": dict(sorted(label_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "split_label_counts": split_label_counts,
        "decision_content_hash": decisions["decision_content_hash"],
        "label_content_hash": labels_payload["label_content_hash"],
        "split_content_hash": manifest["split_content_hash"],
        "graph_data_hash": graph_data_hash,
        "engineering_smoke_training_ready": set(label_counts) == {"0", "1"},
        "research_training_ready": False,
        "research_blocking_reasons": [
            "only five promoted positive graphs from five independent incidents",
            "only fifty promoted negative graphs",
            "agent-assisted evidence review does not replace research-grade human sign-off",
            "protocol-role dictionary coverage remains below the research threshold",
        ],
    }
    write_json(root / args.snapshot, snapshot)

    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "labels": len(items),
        "label_counts": dict(sorted(label_counts.items())),
        "groups": len(groups),
        "split_counts": dict(sorted(split_counts.items())),
        "split_label_counts": split_label_counts,
        "targets_by_label": targets_by_label,
        "split_content_hash": manifest["split_content_hash"],
        "graph_data_hash": graph_data_hash,
        "held_out_test_frozen": True,
        "engineering_smoke_training_ready": snapshot["engineering_smoke_training_ready"],
        "research_training_ready": False,
        "outputs": [args.out, args.snapshot, args.split_dir],
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
