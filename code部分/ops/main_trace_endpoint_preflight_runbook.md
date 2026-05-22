# Main Trace Endpoint Preflight Runbook

## Purpose

Preflight the trace-capable Ethereum mainnet endpoint configured in
`.env.local` as `ETH_MAIN_HTTP_URL`.

The report redacts URL paths and does not write API keys.

## Configure

Add this to `.env.local` after receiving a trace-capable endpoint:

```bash
export ETH_MAIN_HTTP_URL="https://your-trace-capable-mainnet-endpoint"
```

## Dry Run

Validate URL shape without making network calls:

```bash
python3 scripts/main_trace_endpoint_preflight.py \
  --env-file .env.local \
  --dry-run \
  --out ops/reports/trace-endpoint-preflight.plan.json
```

## Real Preflight

```bash
python3 scripts/main_trace_endpoint_preflight.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

Proceed only if the report returns `status=ok` with `selected_method`.

## Self-Test

```bash
python3 scripts/main_trace_endpoint_preflight_selftest.py
```
