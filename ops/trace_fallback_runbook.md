# Provider-only TraceBundle Fallback Runbook

Use this when local Geth/Erigon trace APIs are unavailable.

```bash
python3 scripts/provider_trace_fallback.py \
  --input data/replay/pending-tx.v1 \
  --summary-out ops/reports/trace-fallback.latest.json
```

Validate replay output:

```bash
python3 scripts/trace_replay_check.py \
  --input data/replay/trace-bundle.v1 \
  --out ops/reports/trace-replay-check.latest.json
```

The generated `TraceBundle` records use:

```json
{
  "trace_source": "provider_fallback",
  "trace_status": "unsupported",
  "calls": [],
  "logs": [],
  "state_diff": {}
}
```

This keeps the downstream pipeline alive while making the missing trace source
explicit and auditable.

