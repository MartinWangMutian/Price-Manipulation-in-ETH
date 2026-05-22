#!/usr/bin/env python3
"""Synthetic checks for protocol_role_enricher.py."""

from __future__ import annotations

from protocol_role_enricher import build_protocol_features


def main() -> int:
    aave_pool = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
    chainlink = "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419"
    parsed = {
        "event_id": "parsed-source",
        "schema_ver": "parsed-trace.v1",
        "chain_id": 1,
        "created_at": "2026-05-14T00:00:00.000+00:00",
        "idempotency_key": "1:0x" + "cd" * 32 + ":debug_traceCall:parsed-trace.v1",
        "tx_hash": "0x" + "cd" * 32,
        "calls": [{"ordinal": 0, "from": "0x" + "11" * 20, "to": aave_pool}],
        "token_transfers": [
            {
                "event_id": "transfer-1",
                "token": "0x" + "22" * 20,
                "from": chainlink,
                "to": "0x" + "33" * 20,
            }
        ],
        "feature_missing_flags": [],
    }
    role_index = {
        aave_pool: {
            "protocol_id": "aave_v3_ethereum",
            "category": "lending",
            "contract": "Pool",
            "roles": ["pool", "lending_market", "liquidation_module"],
            "graph_node_type": "protocol",
            "emergency_surface": True,
        },
        chainlink: {
            "protocol_id": "chainlink_eth_usd",
            "category": "oracle",
            "contract": "ETH/USD Feed Proxy",
            "roles": ["oracle"],
            "graph_node_type": "protocol",
            "emergency_surface": False,
        },
    }
    record = build_protocol_features(parsed, role_index)
    assert len(record["matched_protocol_roles"]) == 2, record
    assert len(record["call_protocol_annotations"]) == 1, record
    assert len(record["transfer_protocol_annotations"]) == 1, record
    role_sets = [set(item["roles"]) for item in record["matched_protocol_roles"]]
    assert any("lending_market" in roles for roles in role_sets), record
    assert any("oracle" in roles for roles in role_sets), record
    assert "no_protocol_role_matches" not in record["feature_missing_flags"], record
    print("protocol_role_enricher_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
