# Alert Orchestrator Runbook

## Purpose

Create `alert-event.v1` replay records from `risk-score.v1`, attach graph/trace evidence references, route by severity, and write an audit log.

## Command

```bash
python3 scripts/alert_orchestrator.py \
  --risk-input data/replay/risk-score.v1 \
  --graph-input data/replay/graph-inference.v1 \
  --trace-input data/replay/trace-bundle.v1 \
  --write-replay \
  --out ops/reports/alert-orchestrator.latest.json \
  --audit-log ops/audit/alert-orchestrator.jsonl
```

## Severity Routing

- `<0.50`: low
- `0.50-0.75`: watch
- `0.75-0.90`: high
- `>0.90`: critical

High and critical alerts include `trigger_rag_async`. Critical alerts also include placeholders for approved suggested transaction preparation and incident runbook steps.

## Replay Check

```bash
python3 scripts/alert_replay_check.py \
  --input data/replay/alert-event.v1 \
  --audit-log ops/audit/alert-orchestrator.jsonl \
  --out ops/reports/alert-replay-check.latest.json
```
