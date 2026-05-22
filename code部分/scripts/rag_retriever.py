#!/usr/bin/env python3
"""Hybrid dense+sparse retrieval over the local RAG seed index."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_index_builder import VECTOR_DIMS, dense_vector, tokens


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def sparse_query(query: str) -> dict[str, int]:
    return dict(Counter(tokens(query)))


def dot(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def sparse_score(query_terms: dict[str, int], doc_terms: dict[str, int]) -> float:
    return sum(min(count, doc_terms.get(term, 0)) for term, count in query_terms.items())


def rank_scores(scores: dict[str, float]) -> dict[str, int]:
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return {doc_id: rank + 1 for rank, (doc_id, score) in enumerate(ordered) if score > 0}


def retrieve(index: dict[str, Any], query: str, top_k: int = 5) -> dict[str, Any]:
    query_terms = sparse_query(query)
    query_vector = dense_vector(query_terms)
    dense_scores: dict[str, float] = {}
    sparse_scores: dict[str, float] = {}
    doc_by_id: dict[str, dict[str, Any]] = {}
    corpus_terms: set[str] = set()
    for entry in index.get("documents", []):
        corpus_terms.update(entry.get("sparse_terms", {}).keys())
    if not (set(query_terms) & corpus_terms):
        return {
            "query": query,
            "null_retrieval": True,
            "null_reason": "no_dense_or_sparse_hits",
            "hits": [],
        }
    for entry in index.get("documents", []):
        doc = entry["doc"]
        doc_id = doc["doc_id"]
        doc_by_id[doc_id] = entry
        dense_scores[doc_id] = dot(query_vector, entry.get("dense_vector", [0.0] * VECTOR_DIMS))
        sparse_scores[doc_id] = sparse_score(query_terms, entry.get("sparse_terms", {}))

    dense_ranks = rank_scores(dense_scores)
    sparse_ranks = rank_scores(sparse_scores)
    rrf_scores: dict[str, float] = {}
    for doc_id in set(dense_ranks) | set(sparse_ranks):
        score = 0.0
        if doc_id in dense_ranks:
            score += 1.0 / (60 + dense_ranks[doc_id])
        if doc_id in sparse_ranks:
            score += 1.0 / (60 + sparse_ranks[doc_id])
        rrf_scores[doc_id] = score

    ranked = sorted(rrf_scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    hits = []
    for doc_id, score in ranked:
        entry = doc_by_id[doc_id]
        doc = entry["doc"]
        hits.append(
            {
                "doc_id": doc_id,
                "source_type": doc["source_type"],
                "protocol": doc["protocol"],
                "section": doc["section"],
                "severity": doc["severity"],
                "source_url": doc["source_url"],
                "evidence_ref": entry["evidence_ref"],
                "rrf_score": round(score, 6),
                "dense_score": round(dense_scores.get(doc_id, 0.0), 6),
                "sparse_score": sparse_scores.get(doc_id, 0.0),
                "evidence_template": f"[{entry['evidence_ref']}] {doc['protocol']} / {doc['section']}: {doc['text']}",
            }
        )
    return {
        "query": query,
        "null_retrieval": not hits,
        "null_reason": "no_dense_or_sparse_hits" if not hits else None,
        "hits": hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local hybrid RAG retrieval.")
    parser.add_argument("--index", default="data/rag/index/knowledge-snapshot.seed-2026-05-14.json")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", default="ops/reports/rag-retriever.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    index = read_json(root / args.index)
    result = retrieve(index, args.query, args.top_k)
    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "knowledge_snapshot": index.get("knowledge_snapshot"),
        **result,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
