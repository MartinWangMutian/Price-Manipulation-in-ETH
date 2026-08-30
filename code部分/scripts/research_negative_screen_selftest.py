#!/usr/bin/env python3
"""Synthetic checks for the Stage 8 negative candidate screen."""

from __future__ import annotations

from research_negative_screen import classify


def main() -> int:
    queue_item = {
        "tx_hash": "0x" + "1" * 64,
        "from": "0x" + "2" * 40,
        "to": "0x" + "3" * 40,
    }
    graph = {
        "nodes": [{"node_type": "address", "address": "0x" + "4" * 40}],
        "edges": [
            {"edge_type": "call", "call_depth": 9, "success": True, "semantic_action": "swap"}
            for _ in range(16)
        ],
    }
    thresholds = {"call_edges_min": 15, "transfer_edges_min": 10, "max_call_depth_min": 8}
    clean = classify(queue_item, graph, set(), set(), set(), thresholds)
    assert clean["review_status"] == "screen_pass_human_review_required"
    assert clean["candidate_label"] is None
    assert clean["hard_negative_candidate"] is True

    blocked = classify(
        queue_item,
        graph,
        {queue_item["tx_hash"]},
        {queue_item["to"]},
        set(),
        thresholds,
    )
    assert blocked["review_status"] == "blocked_unlabeled"
    assert len(blocked["blockers"]) == 2
    print("research_negative_screen_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
