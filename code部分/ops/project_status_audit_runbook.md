# Project Status Audit Runbook

## Purpose

Aggregate local replay, readiness, go/no-go, and validation reports into a single status report and blocker register.

## Command

```bash
python3 scripts/project_status_audit.py \
  --out ops/reports/project-status.latest.json \
  --blockers ops/blocker_register.md
```
