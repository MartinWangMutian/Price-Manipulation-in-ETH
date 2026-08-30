#!/usr/bin/env python3
"""Dependency-free feature checks for graphsage_model.py."""

from __future__ import annotations

from graphsage_model import (
    EDGE_SUMMARY_DIM,
    FEATURE_DIM,
    CashFlowGraphSAGE,
    GraphSAGEConfig,
    dependency_status,
    graph_tensors,
    incident_edge_features,
    node_feature,
)


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
    if all(dependency_status().values()):
        import torch

        x, edge_index, batch = graph_tensors([graph])
        for layers in (1, 2, 3):
            model = CashFlowGraphSAGE(
                GraphSAGEConfig(hidden_dim=8, num_layers=layers, dropout=0.0)
            )
            logits = model.forward_logits(x, edge_index, batch)
            probabilities = model(x, edge_index, batch)
            assert tuple(logits.shape) == (1,)
            assert torch.allclose(probabilities, torch.sigmoid(logits))
    print("graphsage_model_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
