#!/usr/bin/env python3
"""Synthetic checks for the Stage 8 expansion audit."""

from __future__ import annotations

from copy import deepcopy

from research_expansion_audit import audit_payloads


def queue(items: list[dict]) -> dict:
    return {"trace_method": "trace_transaction", "items": items}


def item(tx_hash: str, label_marker: bool = False) -> dict:
    result = {"tx_hash": tx_hash, "preferred_rpc_methods": ["trace_transaction"]}
    if label_marker:
        result["candidate_label"] = None
    return result


def main() -> int:
    positive_hash = "0x" + "1" * 64
    negative_hash = "0x" + "2" * 64
    payloads = {
        "config": {
            "trace_method": "trace_transaction",
            "targets": {"independent_attack_events": 1, "positive_rich_graphs": 10, "negative_rich_graphs": 20},
            "paid_call_guards": {"forbid_debug_trace_transaction": True, "pilot_positive_count": 1, "pilot_negative_count": 1},
            "split_policy": {"held_out_split": "held_out_test"},
        },
        "index": {"status": "ready_for_pilot", "research_target_complete": False, "progress": {"verified_independent_events": 1, "current_promoted_positive_rich_graphs": 1, "current_promoted_negative_rich_graphs": 2}},
        "full_positive": queue([item(positive_hash)]),
        "pilot_positive": queue([item(positive_hash)]),
        "pilot_negative": queue([item(negative_hash, True)]),
        "sampler": {"status": "ok", "selected_count": 1, "trace_calls_performed": 0, "rpc_call_attempts": 3},
        "failed_sampler": {"status": "failed_stopped", "trace_calls_performed": 0},
        "positive_trace": {"status": "ok", "method": "trace_transaction", "ok_trace_bundles": 1, "failed_trace_bundles": 0, "attempts": [{"selected": "trace_transaction"}], "rpc_call_summary": {"trace_attempts": 1}},
        "negative_trace": {"status": "ok", "method": "trace_transaction", "ok_trace_bundles": 1, "failed_trace_bundles": 0, "attempts": [{"selected": "trace_transaction"}], "rpc_call_summary": {"trace_attempts": 1}},
        "raw_manifest": {"expected_transactions": 2, "entries": [{"tx_hash": positive_hash}, {"tx_hash": negative_hash}]},
        "quality": {"status": "ok", "errors": [], "audited": {"graphs": 2}, "expected": {"exploit_graphs": 1, "normal_graphs": 1}},
        "screen": {"candidate_label": None, "human_review_completed": False, "items": [{"tx_hash": negative_hash, "candidate_label": None, "hard_negative_candidate": True, "review_status": "screen_pass_human_review_required", "positive_anchor_overlap": False}]},
        "split": {"groups": [{"split": "held_out_test", "tx_hashes": ["0x" + "f" * 64]}]},
    }
    report = audit_payloads(payloads)
    assert report["status"] == "pilot_ok_target_incomplete", report
    assert report["pilot"]["labels_promoted"] == 0
    bad = deepcopy(payloads)
    bad["pilot_negative"]["items"][0]["candidate_label"] = 0
    failed = audit_payloads(bad)
    assert failed["status"] == "failed"
    print("research_expansion_audit_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
