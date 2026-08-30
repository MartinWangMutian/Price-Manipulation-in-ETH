#!/usr/bin/env python3
"""Synthetic checks for the Stage 8 negative metadata sampler."""

from __future__ import annotations

from research_negative_sampler import metadata_score, select_candidates


def tx(index: int, gas: int = 300000, input_size: int = 128) -> dict:
    return {
        "hash": "0x" + f"{index:064x}",
        "from": "0x" + f"{index + 100:040x}",
        "to": "0x" + f"{index + 200:040x}",
        "gas": hex(gas),
        "value": "0x0",
        "input": "0x" + "ab" * input_size,
        "block_offset": -8000 - index,
    }


def main() -> int:
    anchor = tx(999, gas=320000, input_size=140)
    close = tx(1, gas=310000, input_size=136)
    far = tx(2, gas=5_000_000, input_size=8)
    assert metadata_score(close, anchor) > metadata_score(far, anchor)

    invalid = {**tx(3), "input": "0x"}
    excluded = tx(4)
    selected, skipped = select_candidates(
        [far, close, invalid, excluded, close],
        anchor,
        {excluded["hash"]},
        set(),
        100000,
        2,
        42,
        1,
    )
    assert [item["hash"] for item in selected] == [close["hash"], far["hash"]]
    assert skipped["not_contract_call"] == 1
    assert skipped["excluded_hash"] == 1
    assert skipped["duplicate_hash"] == 1
    print("research_negative_sampler_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
