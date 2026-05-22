# Failure Drill Runbook

## Purpose

Run a simulated P6-D failure drill over provider-only replay outputs.

## Command

```bash
python3 scripts/failure_drill.py \
  --node-health ops/reports/node-health.latest.json \
  --trace-report ops/reports/pending-trace-worker.latest.json \
  --rag-timeout-report ops/reports/rag-explanation-builder-timeout.latest.json \
  --alert-replay-check ops/reports/alert-replay-check.latest.json \
  --graphs data/replay/graph-inference.v1 \
  --risks data/replay/risk-score.v1 \
  --alerts data/replay/alert-event.v1 \
  --out ops/reports/failure-drill.latest.json \
  --runbook ops/incident_runbook.generated.md
```

## Limitation

This is simulated because local primary and backup nodes are not configured.
