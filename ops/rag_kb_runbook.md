# RAG Knowledge Base Runbook

## Purpose

Build and query the local seed RAG knowledge base for alert explanations.

## Build

```bash
python3 scripts/rag_index_builder.py \
  --documents data/rag/documents.seed.json \
  --out data/rag/index/knowledge-snapshot.seed-2026-05-14.json \
  --report ops/reports/rag-index-builder.latest.json
```

## Query

```bash
python3 scripts/rag_retriever.py \
  --index data/rag/index/knowledge-snapshot.seed-2026-05-14.json \
  --query "oracle manipulation flash loan lending pool" \
  --top-k 5 \
  --out ops/reports/rag-retriever.latest.json
```

## Null Retrieval

If dense and sparse retrieval both produce no hit, the retriever returns:

```json
{
  "null_retrieval": true,
  "null_reason": "no_dense_or_sparse_hits"
}
```
