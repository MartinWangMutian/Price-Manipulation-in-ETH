#!/usr/bin/env python3
"""Synthetic checks for the Stage 8 bounded batch audit."""

from __future__ import annotations

from copy import deepcopy

from research_batch_audit import audit_batch


def trace(status: str, ok: int, attempts: int, reused: int = 0) -> dict:
    return {
        "status": status,
        "method": "trace_transaction",
        "ok_trace_bundles": ok,
        "reused_existing_bundles": reused,
        "rpc_call_summary": {"trace_attempts": attempts},
        "attempts": [{"selected": "trace_transaction"}] if attempts else [],
    }


def main() -> int:
    positive_hash = "0x" + "1" * 64
    negative_hash = "0x" + "2" * 64
    payloads = {
        "config": {
            "batch_id": "test",
            "trace_method": "trace_transaction",
            "positive_count": 1,
            "negative_count": 1,
            "max_paid_trace_calls": 2,
            "paid_call_guards": {
                "forbid_debug_trace_transaction": True,
                "fail_fast": True,
                "skip_existing": True,
                "stop_after_batch": True,
                "provider_usage_limit_confirmed_by_user": True,
            },
        },
        "builder": {"status": "ready_for_paid_dry_run", "errors": []},
        "positive_queue": {"items": [{"tx_hash": positive_hash}]},
        "negative_queue": {"items": [{"tx_hash": negative_hash, "candidate_label": None}]},
        "positive_initial": trace("degraded", 1, 1),
        "positive_resume": trace("ok", 1, 0, reused=1),
        "negative_trace": trace("ok", 1, 1),
        "raw_manifest": {"expected_transactions": 2, "entries": [{"tx_hash": positive_hash}, {"tx_hash": negative_hash}]},
        "trace_audit": {"status": "ok", "normalized_trace_files": 2, "trace_source_counts": {"trace_transaction": 2}},
        "quality": {"status": "ok", "errors": [], "audited": {"graphs": 2}, "cohort_stats": {}, "feature_missing_flags": {}},
        "screen": {"candidate_count": 1, "screened_count": 1, "labels_promoted": 0, "human_review_completed": False, "known_exploit_transaction_hash_hits": 0, "ofac_sdn_graph_address_hits": 0, "positive_anchor_overlaps": 0, "hard_negative_candidates": 0},
        "split": {"groups": [{"split": "held_out_test", "tx_hashes": ["0x" + "f" * 64]}]},
        "metadata_failure": {"status": "insufficient_candidates", "trace_calls_performed": 0},
        "metadata_corrected": {"status": "ok", "selected_count": 5},
    }
    report = audit_batch(payloads)
    assert report["status"] == "batch_ok_review_pending_target_incomplete", report
    bad = deepcopy(payloads)
    bad["negative_queue"]["items"][0]["candidate_label"] = 0
    assert audit_batch(bad)["status"] == "failed"
    print("research_batch_audit_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
