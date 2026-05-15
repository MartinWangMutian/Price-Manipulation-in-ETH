# Label Readiness Audit Runbook

## Purpose

Aggregate exploit and normal candidate reports into one readiness check. This
audit answers whether candidate queues are ready to run against a trace endpoint.
It does not mark labels training-ready.

## Command

```bash
python3 scripts/label_readiness_audit.py \
  --out ops/reports/label-readiness-audit.latest.json
```

## Interpretation

- `status=trace_ready`: candidate hashes and dry-runs are ready for real trace replay.
- `training_ready=false`: expected until traces are replayed and analyst-promoted.
