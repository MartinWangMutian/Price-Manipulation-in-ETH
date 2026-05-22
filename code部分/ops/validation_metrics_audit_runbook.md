# Validation Metrics Audit Runbook

## Purpose

Map the validation metrics checklist to current local reports.

## Command

```bash
python3 scripts/validation_metrics_audit.py \
  --out ops/reports/validation-metrics-audit.latest.json
```

## Expected Current Result

`not_pass`, because GraphSAGE quality metrics, live pending/trace latency, and high/critical rich evidence metrics require real trace and labeled datasets.
