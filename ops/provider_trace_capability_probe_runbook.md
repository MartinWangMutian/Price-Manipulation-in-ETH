# Provider Trace Capability Probe Runbook

## Purpose

Check whether the already configured third-party provider HTTP endpoint can
temporarily satisfy the Phase B historical trace requirement.

This does not replace the dedicated `ETH_MAIN_HTTP_URL` requirement unless the
probe returns `status=ok` and shows a `selected_method`.

## Command

```bash
python3 scripts/provider_trace_capability_probe.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json
```

The wrapper reads `ETH_PROVIDER_HTTP_URL` from `.env.local` and does not write
the URL or API key to the report.

## Dry Run

Validate `.env.local` without making a network call:

```bash
python3 scripts/provider_trace_capability_probe.py \
  --env-file .env.local \
  --dry-run \
  --out ops/reports/provider-trace-capability-probe.plan.json
```

## Equivalent Manual Command

```bash
source .env.local

python3 scripts/trace_endpoint_preflight.py \
  --rpc-url "$ETH_PROVIDER_HTTP_URL" \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json
```

## Interpret Result

- `status=ok` and `selected_method=debug_traceTransaction` or
  `selected_method=trace_transaction`: the provider can be used for the next
  Phase B replay attempt.
- `status=degraded` with `eth_chainId` ok but trace methods failing: the
  provider works as a normal Ethereum RPC but is not sufficient for historical
  trace replay.
- `status=missing_endpoint`: `.env.local` did not export
  `ETH_PROVIDER_HTTP_URL`.

If the probe passes, set:

```bash
export ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"
```

Then run the standard Phase B endpoint preflight and historical replay commands
from `ops/post_endpoint_trace_runbook.md`.

## Self-Test

```bash
python3 scripts/provider_trace_capability_probe_selftest.py
```
