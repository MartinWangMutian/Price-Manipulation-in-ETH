#!/usr/bin/env python3
"""Build a lightweight local RAG index from seed documents."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
VECTOR_DIMS = 64


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


def tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def sparse_terms(doc: dict[str, Any]) -> dict[str, int]:
    text = " ".join(
        str(doc.get(field, ""))
        for field in ("protocol", "section", "severity", "text", "source_type")
    )
    return dict(Counter(tokens(text)))


def dense_vector(term_counts: dict[str, int]) -> list[float]:
    vector = [0.0] * VECTOR_DIMS
    for token, count in term_counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % VECTOR_DIMS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign * float(count)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def validate_doc(doc: dict[str, Any]) -> list[str]:
    required = {
        "doc_id",
        "schema_ver",
        "source_type",
        "protocol",
        "section",
        "date",
        "severity",
        "text",
        "source_url",
        "retrieved_at",
        "license_note",
    }
    errors: list[str] = []
    missing = sorted(required - set(doc))
    if missing:
        errors.append(f"missing fields {missing}")
    if doc.get("schema_ver") != "rag-document.v1":
        errors.append("schema_ver mismatch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local RAG seed index.")
    parser.add_argument("--documents", default="data/rag/documents.seed.json")
    parser.add_argument("--out", default="data/rag/index/knowledge-snapshot.seed-2026-05-14.json")
    parser.add_argument("--report", default="ops/reports/rag-index-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    corpus = read_json(root / args.documents)
    docs = corpus.get("documents", [])
    errors: list[dict[str, Any]] = []
    indexed_docs: list[dict[str, Any]] = []
    source_counts = Counter()
    protocol_counts = Counter()

    for doc in docs:
        doc_errors = validate_doc(doc)
        if doc_errors:
            errors.append({"doc_id": doc.get("doc_id"), "errors": doc_errors})
            continue
        terms = sparse_terms(doc)
        indexed_docs.append(
            {
                "doc": doc,
                "sparse_terms": terms,
                "dense_vector": dense_vector(terms),
                "evidence_ref": f"doc:{doc['doc_id']}#{doc['section']}",
            }
        )
        source_counts[doc["source_type"]] += 1
        protocol_counts[doc["protocol"]] += 1

    index = {
        "schema_ver": "rag-index.v1",
        "knowledge_snapshot": corpus["knowledge_snapshot"],
        "created_at": now_iso(),
        "retrieval": {
            "dense": "hashing-vector-64",
            "sparse": "token-count",
            "hybrid": "rrf",
            "rerank": "rrf",
        },
        "documents": indexed_docs,
    }
    write_json(root / args.out, index)

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "documents_seen": len(docs),
        "documents_indexed": len(indexed_docs),
        "source_type_counts": dict(sorted(source_counts.items())),
        "protocol_counts": dict(sorted(protocol_counts.items())),
        "knowledge_snapshot": corpus["knowledge_snapshot"],
        "index_path": args.out,
        "errors": errors,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
