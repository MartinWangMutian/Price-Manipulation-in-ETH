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
        "matched_protocol_roles": [
            {
                "address": router,
                "protocol_id": "uniswap_v3_router",
                "category": "router",
                "contract": "UniversalRouter",
                "roles": ["router"],
                "graph_node_type": "protocol",
                "emergency_surface": False,
            }
        ],
        "call_protocol_annotations": [],
        "transfer_protocol_annotations": [],
        "feature_missing_flags": [],
    }
    graph = build_graph(parsed, protocol_features)
    errors = validate_graph_shape(graph)
    assert not errors, errors
    node_types = {node["node_type"] for node in graph["nodes"]}
    edge_types = {edge["edge_type"] for edge in graph["edges"]}
    assert {"transaction", "address", "asset", "protocol"}.issubset(node_types), graph
    assert {"transfer", "call", "context"}.issubset(edge_types), graph
    assert graph["context_windows"] == ["tx-only"], graph
    assert "context_5m_address_unavailable" in graph["feature_missing_flags"], graph
    print("cash_flow_graph_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
