# TraceBundle Audit Runbook

Run the P2-C audit after producing `TraceBundle` replay records:

```bash
python3 scripts/trace_bundle_audit.py \
  --input data/replay/trace-bundle.v1 \
  --out ops/reports/trace-bundle-audit.latest.json
```

The audit verifies:

- `TraceBundle.schema_ver`;
- `tx_hash`;
- `trace_source`;
- `trace_status`;
- `calls`, `logs`, and `state_diff` field types;
- standardized TraceBundle replay file persistence;
- raw trace references for successful `trace_status=ok` traces;
- idempotency-key dedupe count for replayed bundles.

In provider-only mode, raw trace references are expected to be absent because
all bundles are fallback records with `trace_status=unsupported`.

