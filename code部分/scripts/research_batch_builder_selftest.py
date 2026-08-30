#!/usr/bin/env python3
"""Synthetic checks for the bounded Stage 8 batch builder."""

from __future__ import annotations

from copy import deepcopy

from research_batch_builder import build_batch


def main() -> int:
    positive_hash = "0x" + "1" * 64
    negative_hash = "0x" + "2" * 64
    config = {
        "batch_id": "test",
        "trace_method": "trace_transaction",
        "positive_incident_ids": ["incident"],
        "positive_count": 1,
        "negative_per_incident": 1,
        "negative_count": 1,
        "max_paid_trace_calls": 2,
        "paid_call_guards": {
            "forbid_debug_trace_transaction": True,
            "stop_after_batch": True,
        },
        "label_policy": {"automatic_label_promotion": False},
    }
    full_positive = {
        "items": [{
            "incident_id": "incident",
            "tx_hash": positive_hash,
            "preferred_rpc_methods": ["trace_transaction"],
        }]
    }
    split = {"groups": [{"split": "held_out_test", "tx_hashes": ["0x" + "f" * 64]}]}
    negatives = [{
        "items": [{
            "matched_incident_id": "incident",
            "tx_hash": negative_hash,
            "candidate_label": None,
            "preferred_rpc_methods": ["trace_transaction"],
        }]
    }]
    result = build_batch(config, full_positive, split, negatives)
    assert result["report"]["status"] == "ready_for_paid_dry_run", result
    assert result["report"]["labels_promoted"] == 0, result

    bad = deepcopy(negatives)
    bad[0]["items"][0]["candidate_label"] = 0
    failed = build_batch(config, full_positive, split, bad)
    assert failed["report"]["status"] == "failed", failed
    print("research_batch_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
