# Trace Endpoint Preflight Runbook

## Purpose

Check a Geth or Erigon trace endpoint before writing any historical replay
bundles. This preflight calls `eth_chainId` and one historical trace method
against the first item in the queue.

## Auto Detect

```bash
source .env.local
python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

Use the report's `selected_method` for full historical replay.

## Geth

```bash
source .env.local
python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method debug_traceTransaction \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

## Erigon

```bash
source .env.local
python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method trace_transaction \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

Proceed to full historical replay only when this report returns `status=ok`.
