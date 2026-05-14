#!/usr/bin/env python3
"""Synthetic checks for rag_retriever.py."""

from __future__ import annotations

from rag_index_builder import dense_vector, sparse_terms
from rag_retriever import retrieve


def main() -> int:
    docs = [
        {
            "doc_id": "oracle-doc",
            "schema_ver": "rag-document.v1",
            "source_type": "security_report",
            "protocol": "oracle_protocol",
            "section": "oracle_manipulation",
            "date": "2026-05-14",
            "severity": "critical",
            "text": "oracle manipulation flash loan exploit",
            "source_url": "https://example.com/oracle",
            "retrieved_at": "2026-05-14T00:00:00.000+00:00",
            "license_note": "test",
        },
        {
            "doc_id": "amm-doc",
            "schema_ver": "rag-document.v1",
            "source_type": "protocol_doc",
            "protocol": "amm_protocol",
            "section": "pool",
            "date": "2026-05-14",
            "severity": "info",
            "text": "concentrated liquidity pool swap router",
            "source_url": "https://example.com/amm",
            "retrieved_at": "2026-05-14T00:00:00.000+00:00",
            "license_note": "test",
        },
    ]
    entries = []
    for doc in docs:
        terms = sparse_terms(doc)
        entries.append(
            {
                "doc": doc,
                "sparse_terms": terms,
                "dense_vector": dense_vector(terms),
                "evidence_ref": f"doc:{doc['doc_id']}#{doc['section']}",
            }
        )
    index = {"knowledge_snapshot": "test", "documents": entries}
    result = retrieve(index, "flash loan oracle manipulation", top_k=1)
    assert result["hits"], result
    assert result["hits"][0]["doc_id"] == "oracle-doc", result
    null_result = retrieve(index, "zzzzzzzzzz", top_k=3)
    assert null_result["null_retrieval"] is True, null_result
    assert null_result["null_reason"] == "no_dense_or_sparse_hits", null_result
    print("rag_retriever_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
