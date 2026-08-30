#!/usr/bin/env python3
"""Synthetic checks for the Stage 8 negative review packet."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from research_negative_review_packet import build_packet


def main() -> int:
    tx_hash = "0x" + "1" * 64
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        graph_path = root / "graphs/one.json"
        graph_path.parent.mkdir(parents=True)
        graph = {
            "tx_hash": tx_hash,
            "nodes": [{"node_id": "transaction:one", "node_type": "transaction"}],
            "edges": [],
        }
        queue = {"snapshot_id": "test", "items": [{"tx_hash": tx_hash}]}
        screen = {
            "items": [{
                "tx_hash": tx_hash,
                "hard_negative_candidate": False,
                "positive_anchor_overlap": False,
                "blockers": [],
            }]
        }
        packet, markdown = build_packet(
            queue, screen, {tx_hash: (graph_path, graph)}, root
        )
        assert packet["status"] == "ready_for_analyst", packet
        assert packet["labels_promoted"] == 0, packet
        assert packet["items"][0]["analyst_review"]["status"] == "pending", packet
        assert "pending" in markdown
    print("research_negative_review_packet_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
