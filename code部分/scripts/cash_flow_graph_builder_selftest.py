#!/usr/bin/env python3
"""Synthetic checks for cash_flow_graph_builder.py."""

from __future__ import annotations

from cash_flow_graph_builder import build_graph, validate_graph_shape


def main() -> int:
    token = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    sender = "0x1111111111111111111111111111111111111111"
    receiver = "0x2222222222222222222222222222222222222222"
    router = "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"
    parsed = {
        "event_id": "parsed-1",
        "schema_ver": "parsed-trace.v1",
        "chain_id": 1,
        "created_at": "2026-05-14T00:00:00.000+00:00",
        "idempotency_key": "1:0x" + "ef" * 32 + ":debug_traceCall:parsed-trace.v1",
        "tx_hash": "0x" + "ef" * 32,
        "trace_source": "debug_traceCall",
        "trace_status": "ok",
        "source_trace_event_id": "trace-1",
        "source_trace_idempotency_key": "trace-key-1",
        "raw_trace_ref": "data/raw-trace/example.json",
        "parser_ver": "trace-parser.v1",
        "token_transfers": [
            {
                "event_id": "transfer-1",
                "standard": "erc20",
                "token": token,
                "symbol": "USDC",
                "decimals": 6,
                "from": sender,
                "to": receiver,
                "amount_raw": "1500000",
                "amount_norm": "1.5",
                "log_index": 0,
            }
        ],
        "calls": [
            {
                "ordinal": 0,
                "depth": 0,
                "type": "CALL",
                "from": sender,
                "to": router,
                "function_selector": "0x38ed1739",
                "function_name": "swapExactTokensForTokens",
                "success": True,
                "value": "0",
            }
        ],
        "feature_missing_flags": [],
    }
    protocol_features = {
        "event_id": "protocol-1",
        "idempotency_key": "protocol-key-1",
        "feature_enricher_ver": "protocol-role-enricher.v1",
        "matched_protocol_roles": [
            {
                "address": router,
                "protocol_id": "uniswap_v3_router",
                "category": "router",
                "contract": "UniversalRouter",
                "roles": ["router"],
                "graph_node_type": "protocol",
                "audit_status": "audited",
                "governance_control": "uniswap_governance",
                "pause_capability": False,
                "upgradeability": "immutable",
                "risk_tier": "router",
                "emergency_surface": False,
            }
        ],
        "call_protocol_annotations": [],
        "transfer_protocol_annotations": [],
        "feature_missing_flags": [],
    }
    address_context = {
        "items": [
            {
                "address": sender,
                "relation_type": "same_initiator",
                "count": 4,
                "last_seen_at": "2026-05-14T00:04:00.000+00:00",
            }
        ]
    }
    protocol_context = {
        "items": [
            {
                "protocol_id": "uniswap_v3_router",
                "relation_type": "volume_spike",
                "count": 12,
                "volume_usd": 1200000.0,
                "last_seen_at": "2026-05-14T00:05:00.000+00:00",
            }
        ]
    }
    graph = build_graph(parsed, protocol_features, address_context, protocol_context)
    errors = validate_graph_shape(graph)
    assert not errors, errors
    node_types = {node["node_type"] for node in graph["nodes"]}
    edge_types = {edge["edge_type"] for edge in graph["edges"]}
    assert {"transaction", "address", "asset", "protocol", "context"}.issubset(node_types), graph
    assert {"transfer", "call", "context"}.issubset(edge_types), graph
    assert graph["context_windows"] == ["tx-only", "5m-address", "1h-protocol"], graph
    assert graph["lineage"]["trace_bundle_event_id"] == "trace-1", graph
    assert graph["lineage"]["raw_trace_ref"] == "data/raw-trace/example.json", graph
    assert graph["lineage"]["graph_builder_ver"] == "cash-flow-graph-builder.v1", graph
    assert "context_5m_address_unavailable" not in graph["feature_missing_flags"], graph
    protocol_node = next(node for node in graph["nodes"] if node["node_type"] == "protocol")
    assert protocol_node["audit_status"] == "audited", protocol_node
    call_edge = next(edge for edge in graph["edges"] if edge["edge_type"] == "call")
    assert call_edge["semantic_action"] == "swap", call_edge
    temporal_edges = [
        edge
        for edge in graph["edges"]
        if edge.get("edge_type") == "context" and edge.get("context_type") == "temporal_window"
    ]
    assert {edge["window"] for edge in temporal_edges} == {"5m-address", "1h-protocol"}, graph
    print("cash_flow_graph_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
