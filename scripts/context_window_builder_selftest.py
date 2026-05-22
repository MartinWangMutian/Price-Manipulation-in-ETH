#!/usr/bin/env python3
"""Synthetic checks for context_window_builder.py."""

from __future__ import annotations

from context_window_builder import build_contexts, compact_record


def parsed(tx_hash: str, minute: int, sender: str, receiver: str, token: str) -> dict:
    return {
        "tx_hash": tx_hash,
        "created_at": f"2026-05-14T00:{minute:02d}:00.000+00:00",
        "idempotency_key": f"key:{tx_hash}",
        "calls": [
            {
                "ordinal": 0,
                "from": sender,
                "to": receiver,
            }
        ],
        "token_transfers": [
            {
                "from": sender,
                "to": receiver,
                "token": token,
            }
        ],
    }


def main() -> int:
    sender = "0x1111111111111111111111111111111111111111"
    receiver = "0x2222222222222222222222222222222222222222"
    token = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    protocol = {
        "matched_protocol_roles": [
            {
                "protocol_id": "uniswap_v3",
            }
        ]
    }
    first = compact_record(parsed("0x" + "01" * 32, 0, sender, receiver, token), protocol)
    second = compact_record(parsed("0x" + "02" * 32, 4, sender, receiver, token), protocol)
    third = compact_record(parsed("0x" + "03" * 32, 7, sender, receiver, token), protocol)
    assert first is not None and second is not None and third is not None
    address_by_tx, protocol_by_tx = build_contexts([first, second, third])
    second_records = address_by_tx[second["tx_hash"]]
    assert {record["relation_type"] for record in second_records} == {
        "same_asset",
        "same_counterparty",
        "same_initiator",
    }, second_records
    assert protocol_by_tx[second["tx_hash"]][0]["protocol_id"] == "uniswap_v3"
    third_records = address_by_tx[third["tx_hash"]]
    assert any(record["count"] >= 1 for record in third_records), third_records
    print("context_window_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
