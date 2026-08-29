#!/usr/bin/env python3
"""Small deterministic checks for rich_graph_quality_audit.py."""

from __future__ import annotations

from collections import Counter

from rich_graph_quality_audit import stratified_normal_review


def main() -> int:
    items = [
        {"tx_hash": f"0x{index:064x}", "selection_bucket": bucket}
        for index, bucket in enumerate(["call", "call", "transfer", "transfer", "simple", "approve"])
    ]
    selected = stratified_normal_review(items, 4)
    assert len(selected) == 4, selected
    counts = Counter(item["selection_bucket"] for item in selected)
    assert set(counts) == {"approve", "call", "simple", "transfer"}, selected
    assert stratified_normal_review(items, 99) == [
        items[5], items[0], items[4], items[2], items[1], items[3]
    ]
    print("rich_graph_quality_audit_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
