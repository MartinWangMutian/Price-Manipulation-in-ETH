#!/usr/bin/env python3
"""Synthetic checks for Stage 4 label-review feature gates."""

from __future__ import annotations

from stage4_label_review_builder import graph_stats, is_hard_negative


def main() -> int:
    graph = {
        "nodes": [{"node_id": "a"}, {"node_id": "b"}],
        "edges": [
            {
                "edge_type": "call",
                "call_depth": depth,
                "success": depth != 3,
                "semantic_action": "swap" if depth == 2 else None,
            }
            for depth in range(16)
        ]
        + [{"edge_type": "transfer"} for _ in range(2)],
    }
    stats = graph_stats(graph)
    assert stats["call_edges"] == 16
    assert stats["transfer_edges"] == 2
    assert stats["max_call_depth"] == 15
    assert stats["failed_calls"] == 1
    assert stats["semantic_actions"] == ["swap"]
    thresholds = {
        "call_edges_at_least": 15,
        "transfer_edges_at_least": 10,
        "max_call_depth_at_least": 8,
    }
    assert is_hard_negative(stats, thresholds)
    assert not is_hard_negative(
        {"call_edges": 1, "transfer_edges": 0, "max_call_depth": 0}, thresholds
    )
    print("stage4_label_review_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
