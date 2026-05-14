# Pending Trace Worker Runbook

The worker reads `PendingTxEvent` replay records and produces `TraceBundle`
records.

## Provider-only Mode

When no local or dedicated trace endpoints are configured, run:

```bash
python3 scripts/pending_trace_worker.py \
  --input data/replay/pending-tx.v1 \
  --summary-out ops/reports/pending-trace-worker.latest.json
```

Expected provider-only output:

- `trace_source_counts.provider_fallback > 0`
- `trace_status_counts.unsupported > 0`
- `geth_configured = false`
- `erigon_configured = false`

This is an intentional fallback and keeps downstream replay contracts alive.

## Geth Path

When Geth is available:

```bash
export ETH_MAIN_HTTP_URL="http://127.0.0.1:8545"

python3 scripts/pending_trace_worker.py \
  --input data/replay/pending-tx.v1 \
  --summary-out ops/reports/pending-trace-worker-geth.latest.json
```

The worker calls:

```text
debug_traceCall(call, "pending", {"tracer": "callTracer", ...})
```

## Erigon Path

When Erigon is available:

```bash
export ETH_BACKUP_HTTP_URL="http://127.0.0.1:8555"

python3 scripts/pending_trace_worker.py \
  --input data/replay/pending-tx.v1 \
  --summary-out ops/reports/pending-trace-worker-erigon.latest.json
```

The worker calls:

```text
trace_call(call, ["trace", "stateDiff"], "pending")
```

## Validation

```bash
python3 scripts/trace_replay_check.py \
  --input data/replay/trace-bundle.v1 \
  --out ops/reports/trace-replay-check.latest.json
```

