# P5-C RAG Knowledge Base Report

## Scope

Implemented a local seed RAG knowledge base with auditable source metadata and deterministic retrieval.

## Implemented

- `rag-document.v1` schema
- Seed corpus covering protocol docs, audit references, exploit postmortems, security reports, governance proposal, and incident database sources
- Dense hashing-vector retrieval
- Sparse token-count retrieval
- Dense+sparse hybrid retrieval using RRF
- Document evidence template output
- Explicit null retrieval response

## Current Status

This is a seed KB for local replay and explanation plumbing. It stores short source summaries and URLs, not full copied documents.

Current build result:

- documents indexed: 10
- source types: protocol docs, audit reference, governance proposal, exploit postmortems, security reports, incident database
- positive query `oracle manipulation flash loan lending pool`: returned 5 evidence-template hits
- null query: returned `null_retrieval=true` with `null_reason=no_dense_or_sparse_hits`
- index status: ok

## Remaining Gap

Production RAG still needs source-section extraction, immutable raw refs, embedding model selection, and evidence-constrained generation.
