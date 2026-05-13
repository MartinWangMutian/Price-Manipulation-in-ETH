# Phase 0 Data Authorization Register

**Version:** `data-auth.v1`  
**Freeze date:** 2026-05-13

## Authorization Matrix

| Data source | Phase 1 use | Authorization status | Restrictions |
|---|---|---|---|
| Local Ethereum execution node | pending tx, `newHeads`, logs, trace/debug simulation | Approved for internal use | Node data is the primary hot-path source. Do not expose raw payloads externally without review. |
| Backup local execution node | failover for pending tx, heads, logs, trace/debug | Approved for internal use | Same controls as primary local node. |
| Third-party RPC/provider | fallback pending stream, trace/debug supplement, availability comparison | Approved only after provider contract/API terms review | Must not be sole source of truth. Store provider name, endpoint class, request id, and response timestamp. |
| Address labels | alert enrichment, model features, analyst UI | Conditional | Labels are risk references only, not legal facts. Preserve provider, timestamp, confidence, and license terms. |
| Entity attribution | enrichment and analyst review | Conditional | Do not present as definitive identity. Do not export externally without authorization. |
| Security reports | RAG knowledge base, training labels, incident context | Approved for public reports; conditional for commercial feeds | Respect redistribution limits. Store source URL, publisher, publication date, and license notes. |
| Audit reports | RAG knowledge base, protocol risk context | Approved for public reports; conditional for private reports | Cite source sections. Do not leak private audit material. |
| Protocol documentation | contract role mapping, RAG knowledge base | Approved for public docs | Cache source URL and retrieval date. |

## Required Metadata

Every external data artifact must include:

- `source_id`
- `source_type`
- `provider`
- `retrieved_at`
- `license_note`
- `confidence` where applicable
- `raw_ref` or immutable storage reference

## Prohibited Phase 1 Uses

- Treating third-party labels as legal identity.
- Training on private or commercial data without documented license rights.
- Sending raw pending transaction streams, private labels, or commercial
  attribution data to external LLM APIs without separate approval.
- Using third-party RPC/provider output as the only evidence for critical
  on-chain action.

## Review Cadence

Data authorization must be reviewed:

- before Phase 1 provider onboarding;
- before any new paid data source is added;
- before RAG indexes private or commercial documents;
- before external reporting or customer delivery.

