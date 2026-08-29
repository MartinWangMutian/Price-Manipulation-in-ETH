# Post Endpoint Trace Runbook

## Purpose

Run the minimum trace replay path after `ETH_MAIN_HTTP_URL` is configured with a
Geth or Erigon trace-capable endpoint.

## Preconditions

- Root `../.env.local` contains `ETH_PROVIDER_HTTP_URL`; map it to
  `ETH_MAIN_HTTP_URL` only in the replay process.
- `python3 scripts/label_readiness_audit.py --out ops/reports/label-readiness-audit.latest.json`
  returns `status=trace_ready`.

## Commands

```bash
set -a
source ../.env.local
set +a
export ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"
export HISTORICAL_TRACE_METHOD="trace_transaction"

python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method trace_transaction \
  --out ops/reports/trace-endpoint-preflight.latest.json

python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method trace_transaction \
  --retries 1 \
  --fail-fast \
  --skip-existing \
  --out ops/reports/historical-trace-replay.latest.json

python3 scripts/historical_trace_replay.py \
  --queue data/training/normal_trace_replay_queue.v1.json \
  --method trace_transaction \
  --retries 1 \
  --fail-fast \
  --skip-existing \
  --inter-item-delay-s 0.25 \
  --out ops/reports/normal-historical-trace-replay.latest.json

python3 scripts/historical_trace_results_audit.py \
  --exploit-report ops/reports/historical-trace-replay.latest.json \
  --normal-report ops/reports/normal-historical-trace-replay.latest.json \
  --preflight-report ops/reports/trace-endpoint-preflight.latest.json \
  --out ops/reports/historical-trace-results-audit.latest.json

python3 scripts/raw_trace_manifest.py \
  --queue data/training/trace_replay_queue.v1.json \
  --queue data/training/normal_trace_replay_queue.v1.json \
  --bundles data/replay/trace-bundle.v1 \
  --out data/training/raw-trace-manifest.stage2.v1.json \
  --report ops/reports/raw-trace-manifest.latest.json

python3 scripts/trace_replay_check.py \
  --input data/replay/trace-bundle.v1 \
  --allow-replay-duplicates \
  --out ops/reports/trace-replay-check-p2b-deduped.latest.json

python3 scripts/trace_bundle_audit.py \
  --input data/replay/trace-bundle.v1 \
  --out ops/reports/trace-bundle-audit.latest.json

python3 scripts/trace_parser.py \
  --input data/replay/trace-bundle.v1 \
  --write-replay \
  --out ops/reports/trace-parser.latest.json

python3 scripts/protocol_role_enricher.py \
  --input data/replay/parsed-trace.v1 \
  --write-replay \
  --out ops/reports/protocol-role-enricher.latest.json

python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --write-replay \
  --write-snapshot \
  --out ops/reports/cash-flow-graph-builder.latest.json

python3 scripts/label_readiness_audit.py \
  --out ops/reports/label-readiness-audit.latest.json
```

## Safety Note

`historical_trace_replay.py` writes only successful trace bundles by default.
Failed attempts remain in the report. Do not use `--write-failed-bundles` unless
you intentionally need failed bundles for audit testing.
