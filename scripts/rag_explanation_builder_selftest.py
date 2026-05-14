#!/usr/bin/env python3
"""Synthetic checks for rag_explanation_builder.py."""

from __future__ import annotations

from rag_explanation_builder import build_explanation
from rag_index_builder import dense_vector, sparse_terms


def main() -> int:
    tx_hash = "0x" + "56" * 32
    alert = {
        "event_id": "alert-1",
        "schema_ver": "alert-event.v1",
        "chain_id": 1,
        "created_at": "2026-05-14T00:00:00.000+00:00",
        "idempotency_key": f"1:{tx_hash}:alert-event.v1",
        "alert_id": f"alert:{tx_hash}",
        "tx_hash": tx_hash,
        "score": 0.91,
        "severity": "critical",
        "reasons": ["RULE_FLASH_LOAN_PATH"],
        "evidence_refs": ["risk-score:risk-1", "trace:trace-1", "label:none"],
        "suggested_actions": ["trigger_rag_async"],
        "alert_version": "alert-orchestrator.v1",
    }
    graph = {
        "event_id": "graph-1",
        "tx_hash": tx_hash,
        "nodes": [{"node_id": f"tx:{tx_hash}", "node_type": "transaction"}],
        "edges": [],
        "graph_snapshot_ref": "data/graph-snapshots/sample.json",
    }
    doc = {
        "doc_id": "flash-doc",
        "schema_ver": "rag-document.v1",
        "source_type": "security_report",
        "protocol": "flash_protocol",
        "section": "flash_loan",
        "date": "2026-05-14",
        "severity": "critical",
        "text": "flash loan manipulation exploit",
        "source_url": "https://example.com/flash",
        "retrieved_at": "2026-05-14T00:00:00.000+00:00",
        "license_note": "test",
    }
    terms = sparse_terms(doc)
    rag_index = {
        "knowledge_snapshot": "test",
        "documents": [
            {
                "doc": doc,
                "sparse_terms": terms,
                "dense_vector": dense_vector(terms),
                "evidence_ref": "doc:flash-doc#flash_loan",
            }
        ],
    }
    explanation = build_explanation(
        alert,
        {tx_hash: {"path": "graph.json", "record": graph}},
        rag_index,
        "test",
        "local-test",
        top_k=3,
        timeout_ms=2500,
    )
    assert explanation["schema_ver"] == "rag-explanation.v1", explanation
    assert explanation["timeout"] is False, explanation
    assert "score 0.91" in explanation["analyst_note"], explanation
    assert "severity critical" in explanation["analyst_note"], explanation
    assert "RULE_FLASH_LOAN_PATH" in explanation["analyst_note"], explanation
    assert "doc:flash-doc#flash_loan" in explanation["doc_summary"], explanation
    assert explanation["evidence_refs"], explanation
    timeout_explanation = build_explanation(
        alert,
        {tx_hash: {"path": "graph.json", "record": graph}},
        rag_index,
        "test",
        "local-test",
        top_k=3,
        timeout_ms=2500,
        simulate_timeout=True,
    )
    assert timeout_explanation["timeout"] is True, timeout_explanation
    assert "knowledge:test:null" in timeout_explanation["doc_summary"], timeout_explanation
    print("rag_explanation_builder_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
