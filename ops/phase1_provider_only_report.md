# Phase 1 Provider-only Progress Report

**Report time:** 2026-05-13  
**Mode:** provider-only development path  
**Provider role:** `provider-pending-fallback`

## Completed

Provider WebSocket capabilities were verified:

- `newHeads` subscription: ok
- `newPendingTransactions` subscription: ok
- target protocol `logs` subscription: ok

Pending transaction intake was verified:

- 100 new pending transaction hashes collected in the latest run
- 110 total `PendingTxEvent` replay records present
- 110 unique pending idempotency keys
- 0 replay validation errors
- 0 duplicate pending idempotency keys

Provider-only trace fallback was verified:

- 110 fallback `TraceBundle` replay records generated
- `trace_source=provider_fallback`
- `trace_status=unsupported`
- 110 unique trace idempotency keys
- 0 trace replay validation errors
- 0 duplicate trace idempotency keys

## Reports

- `ops/reports/provider-smoke.latest.json`
- `ops/reports/pending-listener-100.latest.json`
- `ops/reports/pending-replay-check-100.latest.json`
- `ops/reports/trace-fallback-100.latest.json`
- `ops/reports/trace-replay-check-100.latest.json`

## Boundary

This does not fully satisfy the Phase 1 Gate. The full gate still requires:

- primary local or dedicated Geth execution node;
- backup local or dedicated Erigon execution node;
- `debug_traceCall` validation on Geth;
- `trace_call` validation on Erigon;
- local/dedicated pending transaction simulation sample of at least 100
  transactions;
- access to `txpool`, peer health, and unrestricted trace/debug namespaces.

Provider-only mode is sufficient to continue development of ingestion, schema,
replay, idempotency, and downstream fallback behavior.

