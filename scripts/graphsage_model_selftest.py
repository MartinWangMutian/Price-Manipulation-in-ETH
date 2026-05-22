#!/usr/bin/env python3
"""Synthetic checks for GraphSAGE model utilities."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from graphsage_model import (
    CashFlowGraphSAGE,
    FEATURE_DIM,
    GraphSAGEConfig,
    dependency_status,
    graph_tensors,
    load_manifest,
    node_feature,
    write_manifest,
)


def main() -> int:
    protocol_node = {
        "node_id": "protocol:0x1",
        "node_type": "protocol",
        "roles": ["router", "pool"],
        "audit_status": "audited",
        "pause_capability": False,
        "emergency_surface": False,
        "risk_tier": "core",
    }
    assert len(node_feature(protocol_node)) == FEATURE_DIM
    config = GraphSAGEConfig(model_version="graphsage.selftest")
    with TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / "manifest.json"
        write_manifest(manifest_path, config, {"training_graphs": 1})
        manifest = load_manifest(manifest_path)
        assert manifest["model_version"] == "graphsage.selftest", manifest
        assert manifest["training_graphs"] == 1, manifest

    graph = {
        "schema_ver": "graph-inference.v1",
        "nodes": [
            {"node_id": "tx:0xabc", "node_type": "transaction", "trace_status": "ok"},
            {"node_id": "address:0x1", "node_type": "address"},
            protocol_node,
        ],
        "edges": [
            {
                "edge_type": "call",
                "from_node": "address:0x1",
                "to_node": "protocol:0x1",
            }
        ],
    }
    deps = dependency_status()
    if all(deps.values()):
        x, edge_index, batch = graph_tensors([graph])
        assert x.shape[1] == FEATURE_DIM, x.shape
        assert edge_index.shape[0] == 2, edge_index.shape
        model = CashFlowGraphSAGE(config)
        score = model(x, edge_index, batch)
        assert score.numel() == 1, score
    else:
        try:
            CashFlowGraphSAGE(config)
        except RuntimeError:
            pass
        else:
            raise AssertionError("CashFlowGraphSAGE should require optional ML dependencies")
    print("graphsage_model_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
