#!/usr/bin/env python3
"""Synthetic checks for Stage 4 grouping and allocation."""

from __future__ import annotations

from grouped_split_builder import assign_groups, related_negative_pairs, target_counts


def main() -> int:
    ratios = {"train": 0.6, "validation": 0.2, "held_out_test": 0.2}
    assert target_counts(5, ratios) == {"train": 3, "validation": 1, "held_out_test": 1}
    assert target_counts(50, ratios) == {"train": 30, "validation": 10, "held_out_test": 10}

    groups = {}
    for index in range(5):
        group_id = f"incident:{index}"
        groups[group_id] = {"group_id": group_id, "label": 1, "tx_hashes": [f"p{index}"]}
    for index, size in enumerate([3, 2, 2, 2, 2, 2] + [1] * 37):
        group_id = f"normal:{index}"
        groups[group_id] = {
            "group_id": group_id,
            "label": 0,
            "tx_hashes": [f"n{index}-{offset}" for offset in range(size)],
        }
    assignments, targets = assign_groups(groups, ratios, 20260830)
    counts = {str(label): {split: 0 for split in ratios} for label in (0, 1)}
    for group_id, split in assignments.items():
        group = groups[group_id]
        counts[str(group["label"])][split] += len(group["tx_hashes"])
    assert counts == targets, (counts, targets)

    normal_items = [
        {"tx_hash": "a", "from": "shared", "to": "x"},
        {"tx_hash": "b", "from": "shared", "to": "y"},
        {"tx_hash": "c", "from": "other", "to": "z"},
    ]
    observed = {
        "a": "2026-01-01T00:00:00+00:00",
        "b": "2026-01-01T00:01:00+00:00",
        "c": "2026-01-01T00:01:00+00:00",
    }
    relations = related_negative_pairs(normal_items, observed, 900, 5)
    assert len(relations) == 1 and set(relations[0][:2]) == {"a", "b"}, relations
    print("grouped_split_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
