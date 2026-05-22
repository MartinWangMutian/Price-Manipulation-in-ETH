# Historical Trace Replay Runbook

## Purpose

Replay candidate exploit transactions from `trace_replay_queue.v1.json` through a
real Geth or Erigon trace endpoint and write `trace-bundle.v1` records.

## Dry Run

```bash
python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --dry-run \
  --out ops/reports/historical-trace-replay.latest.json
```

## Geth

```bash
source .env.local
python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method debug_traceTransaction \
  --out ops/reports/historical-trace-replay.latest.json
```

## Erigon

```bash
source .env.local
python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method trace_transaction \
  --out ops/reports/historical-trace-replay.latest.json
```

`ETH_MAIN_HTTP_URL` must point to a trace-capable endpoint.

Use `--method auto` when the endpoint client is unknown. It tries
`debug_traceTransaction` first, then `trace_transaction`.

By default, only successful traces are written to `data/replay/trace-bundle.v1`.
Failed attempts are recorded in the report but not persisted as replay bundles.
Use `--write-failed-bundles` only when you intentionally want failed trace
records in replay storage for audit testing.

## Selftest

```bash
python3 scripts/historical_trace_replay_selftest.py
```
