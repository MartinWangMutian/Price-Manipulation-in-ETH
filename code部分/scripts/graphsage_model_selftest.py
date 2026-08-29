#!/usr/bin/env python3
"""Dependency-free feature checks for graphsage_model.py."""

from __future__ import annotations

from graphsage_model import EDGE_SUMMARY_DIM, FEATURE_DIM, incident_edge_features, node_feature


def main() -> int:
    left = {"node_id": "address:left", "node_type": "address"}
    right = {"node_id": "protocol:right", "node_type": "protocol", "roles": ["pool"]}
    graph = {
        "nodes": [left, right],
        "edges": [
            {
                "edge_type": "call",
                "from_node": "address:left",
                "to_node": "protocol:right",
                "semantic_action": "flash_loan",
                "call_depth": 2,
                "success": False,
            }
        ],
    }
    incident = incident_edge_features(graph)
    assert len(incident["address:left"]) == EDGE_SUMMARY_DIM
    assert any(incident["address:left"]), incident
    assert len(node_feature(left, incident["address:left"])) == FEATURE_DIM
    print("graphsage_model_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
