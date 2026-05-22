#!/usr/bin/env python3
"""Small synthetic checks for trace_parser.py."""

from __future__ import annotations

from trace_parser import parse_trace_bundle


def word(value: int) -> str:
    return "0x" + f"{value:064x}"


def topic_address(address: str) -> str:
    return "0x" + address.lower().removeprefix("0x").rjust(64, "0")


def main() -> int:
    token = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    sender = "0x1111111111111111111111111111111111111111"
    receiver = "0x2222222222222222222222222222222222222222"
    bundle = {
        "event_id": "trace-source",
        "schema_ver": "trace-bundle.v1",
        "chain_id": 1,
        "created_at": "2026-05-14T00:00:00.000+00:00",
        "idempotency_key": "1:0x" + "ab" * 32 + ":debug_traceCall",
        "tx_hash": "0x" + "ab" * 32,
        "trace_source": "debug_traceCall",
        "trace_status": "ok",
        "calls": [
            {
                "type": "CALL",
                "from": sender,
                "to": token,
                "input": "0xa9059cbb" + "00" * 32,
                "value": "0x0",
                "depth": 0,
            },
            {
                "type": "CALL",
                "from": sender,
                "to": receiver,
                "input": "0x095ea7b3" + "00" * 32,
                "value": "0x0",
                "depth": 1,
                "error": "execution reverted",
            },
        ],
        "logs": [
            {
                "address": token,
                "topics": [
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                    topic_address(sender),
                    topic_address(receiver),
                ],
                "data": word(1_500_000),
                "logIndex": "0x0",
            },
            {
                "address": "0x3333333333333333333333333333333333333333",
                "topics": [
                    "0xc3d58168c5ae7397731d063d5bbf3d6d37f186a5b44a5fbf0aecd7d43b1c7a",
                    topic_address(sender),
                    topic_address(sender),
                    topic_address(receiver),
                ],
                "data": word(7) + word(3).removeprefix("0x"),
                "logIndex": "0x1",
            },
        ],
        "state_diff": {},
    }
    selector_dict = {
        "0xa9059cbb": {"signature": "transfer(address,uint256)", "name": "transfer"},
        "0x095ea7b3": {"signature": "approve(address,uint256)", "name": "approve"},
    }
    metadata_cache = {
        token: {"symbol": "USDC", "decimals": 6, "asset_type": "erc20"}
    }
    parsed = parse_trace_bundle(bundle, selector_dict, metadata_cache)
    assert len(parsed["token_transfers"]) == 2, parsed
    erc20 = parsed["token_transfers"][0]
    assert erc20["standard"] == "erc20", erc20
    assert erc20["amount_raw"] == "1500000", erc20
    assert erc20["amount_norm"] == "1.5", erc20
    erc1155 = parsed["token_transfers"][1]
    assert erc1155["standard"] == "erc1155", erc1155
    assert erc1155["token_id"] == "7", erc1155
    assert erc1155["amount_raw"] == "3", erc1155
    assert len(parsed["calls"]) == 2, parsed
    assert parsed["calls"][0]["depth"] == 0, parsed["calls"][0]
    assert parsed["calls"][0]["function_selector"] == "0xa9059cbb", parsed["calls"][0]
    assert parsed["calls"][1]["success"] is False, parsed["calls"][1]
    assert parsed["calls"][1]["revert_reason"] == "execution reverted", parsed["calls"][1]
    print("trace_parser_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
