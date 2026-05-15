# Trace Endpoint Application Guide

## Why This Is Needed

Phase B historical replay needs an Ethereum mainnet HTTP endpoint that supports
at least one of:

- `debug_traceTransaction`
- `trace_transaction`

The current Alchemy Free tier endpoint passed `eth_chainId`, but returned
Free-tier access errors for both trace methods in
`ops/reports/provider-trace-capability-probe.latest.json`.

## Alchemy Path

Alchemy official docs list Trace API and Debug API availability on paid plans,
not the Free tier:

- Trace API Quickstart: https://www.alchemy.com/docs/reference/trace-api-quickstart
- Pricing plans: https://www.alchemy.com/docs/reference/pricing-plans
- `debug_traceTransaction`: https://www.alchemy.com/docs/reference/debug-tracetransaction

Ask for or upgrade to a plan that includes both:

- Trace API
- Debug API

After upgrade, rerun:

```bash
python3 scripts/provider_trace_capability_probe.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json
```

If it returns `status=ok` and `selected_method`, set:

```bash
export ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"
```

Then refresh:

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

## Dedicated Geth Or Erigon Path

If using another provider or self-hosted node, request or configure:

- Ethereum mainnet HTTP endpoint
- `debug_traceTransaction` support, or `trace_transaction` support
- Enough timeout budget for transaction tracing
- No redaction or method block on historical mainnet transactions

After receiving the endpoint, add it to `.env.local`:

```bash
export ETH_MAIN_HTTP_URL="https://your-trace-capable-mainnet-endpoint"
```

Then run:

```bash
python3 scripts/main_trace_endpoint_preflight.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

Proceed only if the preflight returns `status=ok` with `selected_method`.
