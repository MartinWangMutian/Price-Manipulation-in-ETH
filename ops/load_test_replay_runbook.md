# Replay Load Test Runbook

## Purpose

Run local replay-based latency measurements for P6-C. This is not a live node/provider load test.

## Command

```bash
python3 scripts/load_test_replay.py \
  --pending data/replay/pending-tx.v1 \
  --parsed data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --graphs data/replay/graph-inference.v1 \
  --risks data/replay/risk-score.v1 \
  --alerts data/replay/alert-event.v1 \
  --traces data/replay/trace-bundle.v1 \
  --out ops/reports/load-test-replay.latest.json
```

## Limitation

Live pending listener and trace worker pressure tests require a running stream and a Geth or Erigon trace endpoint.
