#!/usr/bin/env python3
"""GraphSAGE model utilities for cash-flow graph risk scoring."""

from __future__ import annotations

import importlib.util
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


NODE_TYPES = ("transaction", "address", "asset", "protocol", "context")
ROLE_FLAGS = ("oracle", "router", "pool", "lending_market", "liquidation_module")
EDGE_TYPES = ("transfer", "call", "context")
EDGE_ACTIONS = ("flash_loan", "swap", "oracle_read", "borrow", "repay", "liquidation")
EDGE_SUMMARY_DIM = len(EDGE_TYPES) + len(EDGE_ACTIONS) + 4
FEATURE_DIM = len(NODE_TYPES) + len(ROLE_FLAGS) + 8 + EDGE_SUMMARY_DIM


@dataclass(frozen=True)
class GraphSAGEConfig:
    model_version: str = "graphsage.v1"
    feature_ver: str = "cash-flow-graph-builder.v1"
    label_snapshot: str = "label-snapshot.v1"
    threshold_profile: str = "graphsage-thresholds.v1"
    input_dim: int = FEATURE_DIM
    hidden_dim: int = 64
    dropout: float = 0.1
    num_layers: int = 2
    aggregator: str = "mean"


def dependency_status() -> dict[str, bool]:
    return {
        "torch": importlib.util.find_spec("torch") is not None,
        "torch_geometric": importlib.util.find_spec("torch_geometric") is not None,
    }


def require_torch_stack() -> tuple[Any, Any, Any, Any]:
    try:
        import torch
        from torch import nn
        import torch.nn.functional as functional
        from torch_geometric.nn import SAGEConv
    except Exception as exc:  # noqa: BLE001 - report optional stack gaps.
        raise RuntimeError(
            "GraphSAGE requires torch and torch_geometric; install them to train or infer."
        ) from exc
    return torch, nn, functional, SAGEConv


try:
    _torch, _nn, _functional, _SAGEConv = require_torch_stack()

    class CashFlowGraphSAGE(_nn.Module):
        """Two-layer GraphSAGE graph classifier for GraphInferenceRequest records."""

        def __init__(self, config: GraphSAGEConfig):
            super().__init__()
            if config.num_layers != 2:
                raise ValueError("only the validated two-layer GraphSAGE topology is supported")
            self.config = config
            self.conv1 = _SAGEConv(config.input_dim, config.hidden_dim, aggr=config.aggregator)
            self.conv2 = _SAGEConv(config.hidden_dim, config.hidden_dim, aggr=config.aggregator)
            self.dropout = _nn.Dropout(config.dropout)
            self.readout = _nn.Linear(config.hidden_dim, 1)

        def forward(self, x: Any, edge_index: Any, batch: Any) -> Any:
            hidden = self.conv1(x, edge_index)
            hidden = _functional.relu(hidden)
            hidden = self.dropout(hidden)
            hidden = self.conv2(hidden, edge_index)
            hidden = _functional.relu(hidden)
            graph_count = int(batch.max().item()) + 1 if batch.numel() else 1
            # The first NODE_TYPES columns are one-hot node types. Pool only
            # Address and Protocol nodes, falling back to all nodes for a
            # degenerate tx-only graph.
            readout_mask = (x[:, 1] + x[:, 3]) > 0
            if bool(readout_mask.any()):
                hidden = hidden[readout_mask]
                batch = batch[readout_mask]
            pooled = hidden.new_zeros((graph_count, hidden.shape[1]))
            pooled.index_add_(0, batch, hidden)
            counts = hidden.new_zeros((graph_count, 1))
            counts.index_add_(0, batch, hidden.new_ones((hidden.shape[0], 1)))
            pooled = pooled / counts.clamp_min(1.0)
            return _torch.sigmoid(self.readout(pooled)).squeeze(-1)

except RuntimeError:

    class CashFlowGraphSAGE:  # type: ignore[no-redef]
        """Placeholder used when optional ML dependencies are not installed."""

        def __init__(self, config: GraphSAGEConfig):
            raise RuntimeError(
                "GraphSAGE requires torch and torch_geometric; install them to train or infer."
            )


def write_manifest(path: Path, config: GraphSAGEConfig, extra: dict[str, Any] | None = None) -> None:
    payload = {
        "schema_ver": "graphsage-model-manifest.v1",
        **asdict(config),
        "dependencies": dependency_status(),
    }
    if extra:
        payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def node_feature(
    node: dict[str, Any], incident_features: list[float] | None = None
) -> list[float]:
    node_type = str(node.get("node_type", ""))
    values = [1.0 if node_type == item else 0.0 for item in NODE_TYPES]
    roles = {str(role) for role in node.get("roles", []) if isinstance(role, str)}
    values.extend(1.0 if role in roles else 0.0 for role in ROLE_FLAGS)
    values.extend(
        [
            1.0 if node.get("trace_status") == "ok" else 0.0,
            1.0 if node.get("audit_status") == "audited" else 0.0,
            1.0 if node.get("pause_capability") else 0.0,
            1.0 if node.get("emergency_surface") else 0.0,
            1.0 if node.get("risk_tier") in {"core", "oracle"} else 0.0,
            _scaled_number(node.get("count")),
            _scaled_number(node.get("volume_usd")),
            _scaled_number(node.get("price_deviation_bps")),
        ]
    )
    values.extend(incident_features or [0.0] * EDGE_SUMMARY_DIM)
    return values


def _scaled_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number <= 0:
        return 0.0
    return min(math.log1p(number) / 20.0, 1.0)


def graph_tensors(graphs: list[dict[str, Any]]) -> tuple[Any, Any, Any]:
    torch, _, _, _ = require_torch_stack()
    features: list[list[float]] = []
    edges: list[tuple[int, int]] = []
    batch: list[int] = []
    offset = 0
    for graph_index, graph in enumerate(graphs):
        nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
        node_index = {node["node_id"]: offset + idx for idx, node in enumerate(nodes)}
        incident = incident_edge_features(graph, nodes)
        features.extend(node_feature(node, incident.get(node["node_id"])) for node in nodes)
        batch.extend([graph_index] * len(nodes))
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            add_edge_pair(edges, node_index, edge.get("from_node"), edge.get("to_node"))
            if edge.get("asset_node"):
                add_edge_pair(edges, node_index, edge.get("from_node"), edge.get("asset_node"))
                add_edge_pair(edges, node_index, edge.get("asset_node"), edge.get("to_node"))
        offset += len(nodes)
    if not features:
        features = [[0.0] * FEATURE_DIM]
        batch = [0]
    if not edges:
        edges = [(idx, idx) for idx in range(len(features))]
    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
    return (
        torch.tensor(features, dtype=torch.float32),
        edge_index,
        torch.tensor(batch, dtype=torch.long),
    )


def incident_edge_features(
    graph: dict[str, Any], nodes: list[dict[str, Any]] | None = None
) -> dict[str, list[float]]:
    """Summarize typed edge semantics onto incident nodes.

    SAGEConv still uses a compact homogeneous adjacency, while this summary
    prevents transfer/call/context type and action metadata from being silently
    discarded.
    """
    nodes = nodes or [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    raw: dict[str, dict[str, float]] = {
        str(node.get("node_id")): {} for node in nodes if isinstance(node.get("node_id"), str)
    }
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        endpoints = [edge.get("from_node"), edge.get("to_node"), edge.get("asset_node")]
        edge_type = str(edge.get("edge_type") or "")
        action = str(edge.get("semantic_action") or "")
        for endpoint in endpoints:
            if not isinstance(endpoint, str) or endpoint not in raw:
                continue
            values = raw[endpoint]
            if edge_type in EDGE_TYPES:
                values[f"type:{edge_type}"] = values.get(f"type:{edge_type}", 0.0) + 1.0
            if action in EDGE_ACTIONS:
                values[f"action:{action}"] = 1.0
            if edge.get("success") is False:
                values["failed_calls"] = values.get("failed_calls", 0.0) + 1.0
            depth = _scaled_number(edge.get("call_depth", edge.get("depth")))
            values["max_depth"] = max(values.get("max_depth", 0.0), depth)
            amount = _scaled_number(edge.get("value_usd", edge.get("amount_norm")))
            values["amount"] = values.get("amount", 0.0) + amount
            if edge.get("window") in {"5m-address", "1h-protocol"}:
                values["temporal_context"] = 1.0
    result: dict[str, list[float]] = {}
    for node_id, values in raw.items():
        vector = [_scaled_number(values.get(f"type:{name}")) for name in EDGE_TYPES]
        vector.extend(values.get(f"action:{name}", 0.0) for name in EDGE_ACTIONS)
        vector.extend(
            [
                _scaled_number(values.get("failed_calls")),
                values.get("max_depth", 0.0),
                min(values.get("amount", 0.0), 1.0),
                values.get("temporal_context", 0.0),
            ]
        )
        result[node_id] = vector
    return result


def add_edge_pair(
    edges: list[tuple[int, int]],
    node_index: dict[str, int],
    source: Any,
    target: Any,
) -> None:
    if isinstance(source, str) and isinstance(target, str):
        if source in node_index and target in node_index:
            left = node_index[source]
            right = node_index[target]
            edges.append((left, right))
            edges.append((right, left))


def load_graph_records(path: Path) -> list[dict[str, Any]]:
    paths = [path] if path.is_file() else sorted(path.rglob("*.json"))
    records = []
    for item in paths:
        with item.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and payload.get("schema_ver") == "graph-inference.v1":
            records.append(payload)
    return records
