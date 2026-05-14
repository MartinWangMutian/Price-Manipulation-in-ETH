# P2-C TraceBundle Audit Report

**Report time:** 2026-05-14  
**Mode:** provider-only fallback validation

## Audit Result

TraceBundle audit passed with:

- trace bundle files seen: `220`
- normalized trace files: `220`
- unique idempotency keys: `110`
- deduped downstream events: `110`
- validation errors: `0`
- trace sources: `provider_fallback=220`
- trace statuses: `unsupported=220`
- raw trace refs: `0`

The file count is larger than the unique idempotency count because the same
pending replay set was intentionally replayed more than once. Downstream
emission is deduped by `idempotency_key`.

## P2-C Coverage

- `TraceBundle.schema_ver`: checked
- `tx_hash`: checked
- `trace_source`: checked
- `trace_status`: checked
- `calls`, `logs`, `state_diff` field types: checked
- standardized TraceBundle replay persistence: checked
- raw trace persistence: implemented in `pending_trace_worker.py` for
  successful `trace_status=ok` traces; not exercised in provider-only mode
- repeated replay dedupe: checked by unique idempotency count

## Reports

- `ops/reports/trace-bundle-audit.latest.json`
- `ops/reports/trace-replay-check-p2b-deduped.latest.json`

## Remaining Runtime Gap

Successful raw trace persistence requires a local or dedicated Geth/Erigon
endpoint. Provider-only fallback cannot produce raw execution traces.

