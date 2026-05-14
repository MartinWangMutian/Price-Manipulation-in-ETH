#!/usr/bin/env python3
"""Synthetic checks for alert_orchestrator.py."""

from __future__ import annotations

from alert_orchestrator import build_alert


def main() -> int:
    risk = {
        "event_id": "risk-1",
        "schema_ver": "risk-score.v1",
        "chain_id": 1,
        "created_at": "2026-05-14T00:00:00.000+00:00",
        "idempotency_key": "1:0x" + "34" * 32 + ":risk-score.v1",
        "tx_hash": "0x" + "34" * 32,
        "score": 0.91,
        "severity": "critical",
        "reasons": ["RULE_FLASH_LOAN_PATH"],
        "model_version": "rule-baseline.v1",
        "feature_ver": "cash-flow-graph-builder.v1",
        "threshold_profile": "rule-baseline-thresholds.v1",
    }
    routing = {
        "alert_version": "alert-orchestrator.v1",
        "actions": {
            "low": ["store_for_replay"],
            "watch": ["enqueue_analyst_review"],
            "high": ["trigger_rag_async"],
            "critical": [
                "trigger_rag_async",
                "prepare_suggested_transaction_after_approval",
                "attach_incident_runbook_steps",
            ],
        },
    }
    tx_hash = risk["tx_hash"]
    graph_index = {
        tx_hash: {
            "path": "graph.json",
            "record": {
                "event_id": "graph-1",
                "tx_hash": tx_hash,
                "graph_snapshot_ref": "data/graph-snapshots/sample.json",
            },
        }
    }
    trace_index = {tx_hash: {"path": "trace.json", "record": {"event_id": "trace-1"}}}
    alert, warnings = build_alert(risk, routing, graph_index, trace_index)
    assert not warnings, warnings
    assert alert["severity"] == "critical", alert
    assert "trigger_rag_async" in alert["suggested_actions"], alert
    assert "prepare_suggested_transaction_after_approval" in alert["suggested_actions"], alert
    assert "attach_incident_runbook_steps" in alert["suggested_actions"], alert
    assert any(ref.startswith("graph:") for ref in alert["evidence_refs"]), alert
    assert any(ref.startswith("trace:") for ref in alert["evidence_refs"]), alert
    print("alert_orchestrator_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
