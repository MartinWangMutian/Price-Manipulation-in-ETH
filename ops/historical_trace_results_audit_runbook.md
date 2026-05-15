# Historical Trace Results Audit Runbook

## Purpose

Confirm whether exploit and normal historical trace replay has completed after a
trace endpoint is configured.

## Command

```bash
python3 scripts/historical_trace_results_audit.py \
  --exploit-report ops/reports/historical-trace-replay.latest.json \
  --normal-report ops/reports/normal-historical-trace-replay.latest.json \
  --preflight-report ops/reports/trace-endpoint-preflight.latest.json \
  --out ops/reports/historical-trace-results-audit.latest.json
```

## Expected States

- `awaiting_real_replay`: dry-runs are present, but no real endpoint replay yet.
- `ok`: all 57 expected trace bundles are successful and persisted.
- `not_ready`: preflight or replay reports are missing, degraded, or incomplete.
