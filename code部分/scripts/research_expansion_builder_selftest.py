#!/usr/bin/env python3
"""Synthetic checks for the Stage 8 research expansion builder."""

from __future__ import annotations

from copy import deepcopy

from research_expansion_builder import build_outputs


def incident(index: int, status: str = "verified_anchor") -> dict:
    tx_hash = "0x" + f"{index:064x}"
    return {
        "incident_id": f"event_{index}",
        "independent_event_group": f"event_{index}",
        "incident_date": "2024-01-01",
        "affected_protocol": f"Protocol {index}",
        "attack_type": "test",
        "status": status,
        "anchor_transactions": [tx_hash],
        "event_evidence": [{"source_type": "security_report", "url": "https://example.test/report"}],
        "transaction_evidence": [
            {"source_type": "block_explorer", "url": f"https://example.test/tx/{tx_hash}"},
            {"source_type": "reproduction_corpus", "url": "https://example.test/poc"},
        ],
    }


def main() -> int:
    config = {
        "snapshot_id": "test",
        "targets": {
            "independent_attack_events": 2,
            "positive_rich_graphs": 4,
            "negative_rich_graphs": 10,
        },
        "evidence_policy": {
            "qualifying_event_source_types": ["security_report"],
            "required_transaction_source_types": ["block_explorer", "reproduction_corpus"],
            "review_hold_statuses": ["review_hold", "evidence_pending"],
        },
        "split_policy": {"held_out_split": "held_out_test"},
        "negative_sampling": {
            "target_per_event": 5,
            "incident_exclusion_window_blocks": 100,
            "matching_dimensions": ["protocol", "time"],
        },
        "paid_call_guards": {"pilot_positive_count": 1},
        "pilot": {"incident_id": "event_2"},
        "versions": {"queue_schema": "trace-replay-queue.v1", "feature_version": "feature.v1"},
    }
    incidents = {
        "chain": "ethereum",
        "chain_id": 1,
        "incidents": [incident(1), incident(2), incident(3, "review_hold")],
    }
    existing = {
        "items": [
            {
                "tx_hash": incidents["incidents"][0]["anchor_transactions"][0],
            }
        ]
    }
    split = {"groups": [{"split": "held_out_test", "tx_hashes": ["0x" + "f" * 64]}]}
    labels = {"items": [{"label": 1}, {"label": 0}, {"label": 0}]}
    outputs = build_outputs(config, incidents, existing, split, labels)
    assert outputs["report"]["status"] == "ready_for_pilot", outputs["report"]
    assert outputs["report"]["verified_event_target_met"] is True
    assert len(outputs["positive_queue"]["items"]) == 1
    assert len(outputs["pilot_queue"]["items"]) == 1
    assert outputs["negative_plan"]["requested_total"] == 10
    assert outputs["index"]["review_hold_incidents"][0]["incident_id"] == "event_3"

    bad = deepcopy(incidents)
    bad["incidents"][1]["transaction_evidence"] = bad["incidents"][1]["transaction_evidence"][:1]
    failed = build_outputs(config, bad, existing, split, labels)
    assert failed["report"]["status"] == "failed"
    assert any("missing transaction evidence" in value for value in failed["report"]["errors"])
    print("research_expansion_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
