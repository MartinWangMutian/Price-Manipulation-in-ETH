# Phase B Next Action Runbook

## Purpose

Select the next concrete Phase B action from current local reports.

The output is intentionally narrow: one selected action, owner, reason, and
commands if the next action is executable.

## Command

```bash
python3 scripts/phase_b_next_action.py \
  --out ops/reports/phase-b-next-action.latest.json
```

## Self-Test

```bash
python3 scripts/phase_b_next_action_selftest.py
```
