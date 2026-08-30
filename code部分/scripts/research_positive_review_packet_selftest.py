#!/usr/bin/env python3
"""Synthetic checks for the Stage 8 positive review packet."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from research_positive_review_packet import build_packet


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
        queue = {"snapshot_id": "test", "items": [{"tx_hash": tx_hash, "incident_id": "test"}]}
        packet, markdown = build_packet(queue, {tx_hash: (graph_path, graph)}, root)
        assert packet["status"] == "ready_for_analyst", packet
        assert packet["items"][0]["proposed_label"] == 1, packet
        assert packet["items"][0]["label"] is None, packet
        assert "pending" in markdown
    print("research_positive_review_packet_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
