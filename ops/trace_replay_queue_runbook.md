# Trace Replay Queue Runbook

## Purpose

Build a historical trace replay queue from candidate exploit transactions. This
queue is the handoff between label review and a real Geth/Erigon trace endpoint.

## Command

```bash
python3 scripts/trace_replay_queue_builder.py \
  --candidates data/training/replay_label_candidates.seed.json \
  --out data/training/trace_replay_queue.v1.json \
  --report ops/reports/trace-replay-queue-builder.latest.json
```

## Use With Real Endpoint

When `ETH_MAIN_HTTP_URL` points to a Geth or Erigon trace endpoint, replay each
Ethereum item with `debug_traceTransaction` or `trace_transaction`, then promote
only analyst-confirmed results into the training label snapshot.
