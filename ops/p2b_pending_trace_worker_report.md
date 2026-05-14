# P2-B Pending Trace Worker Report

**Report time:** 2026-05-14  
**Mode:** provider-only fallback validation

## Implemented

`scripts/pending_trace_worker.py` implements:

- Geth `debug_traceCall` request path;
- Erigon `trace_call` request path;
- `pending` block tag for both paths;
- call object construction from `PendingTxEvent.tx`;
- normalized `calls`, `logs`, and `state_diff` output fields;
- trace timeout, default `1500 ms`;
- retry policy, default `1` retry;
- standardized trace error objects;
- raw trace persistence for successful trace responses;
- provider fallback `TraceBundle` generation when trace endpoints are missing or fail;
- trace worker summary report with source/status counts.

## Current Validation Result

Current environment has no configured local or dedicated Geth/Erigon endpoint:

- `geth_configured=false`
- `erigon_configured=false`

Provider fallback run:

- input pending replay records: `110`
- written trace bundles: `110`
- `trace_source_counts.provider_fallback=110`
- `trace_status_counts.unsupported=110`
- worker status: `ok`

Trace replay check with replay-deduplication:

- raw trace bundle files seen: `220`
- unique idempotency keys: `110`
- deduped downstream events: `110`
- validation errors: `0`
- status: `ok`

The raw file count is larger than the unique idempotency count because the same
pending replay set was intentionally run more than once. Downstream emission is
deduped by `idempotency_key`.

## Reports

- `ops/reports/pending-trace-worker.latest.json`
- `ops/reports/trace-replay-check-p2b-deduped.latest.json`

## Remaining Runtime Validation

These require local or dedicated node endpoints:

- Geth `debug_traceCall` live validation;
- Erigon `trace_call` live validation;
- successful `trace_status=ok` sample set;
- trace P95 latency measurement against live trace endpoints.

