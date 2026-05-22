# Analyst Console View-model Runbook

## Purpose

Build local analyst console data views from replay artifacts. This is a backend/view-model layer, not a browser UI.

## Build

```bash
python3 scripts/analyst_console_view_builder.py \
  --alerts data/replay/alert-event.v1 \
  --risks data/replay/risk-score.v1 \
  --graphs data/replay/graph-inference.v1 \
  --traces data/replay/trace-bundle.v1 \
  --rag data/replay/rag-explanation.v1 \
  --out-dir data/console \
  --audit-trail data/console/review-audit-trail.v1.jsonl \
  --report ops/reports/analyst-console-view-builder.latest.json
```

## Check

```bash
python3 scripts/analyst_console_view_check.py \
  --console-dir data/console \
  --state-machine config/review_state_machine.json \
  --out ops/reports/analyst-console-view-check.latest.json
```
