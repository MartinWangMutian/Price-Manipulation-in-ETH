# Phase B Completion Audit Runbook

## Purpose

Summarize the Phase B completion gates in one machine-readable report.

This audit does not replace the lower-level reports. It maps their current
statuses to concrete Phase B gates: trace endpoint preflight, historical replay,
label promotion, training readiness, contact handoff, and runbook readiness.

## Command

```bash
python3 scripts/phase_b_completion_audit.py \
  --out ops/reports/phase-b-completion-audit.latest.json
```

## Self-Test

```bash
python3 scripts/phase_b_completion_audit_selftest.py
```

## Expected Current State

Before a trace-capable endpoint and operations contacts are configured, the
expected status is `blocked_user_input`.

Phase B is complete only when `phase_b_complete=true`.
