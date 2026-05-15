# Phase B Refresh Runbook

## Purpose

Refresh local Phase B readiness reports after editing `.env.local` or
`config/ops_contacts.local.json`.

This command does not run live provider trace probes or historical trace replay.
Use it for local gate/status refresh only.

## Command

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

## Outputs

- `ops/reports/phase-b-refresh.latest.json`
- `ops/reports/env-local-audit.latest.json`
- `ops/reports/required-inputs-check.latest.json`
- `ops/reports/phase-b-completion-audit.latest.json`
- `ops/reports/phase-b-next-action.latest.json`
- `ops/reports/artifact-manifest.latest.json`
- `ops/reports/report-secret-audit.latest.json`
- `ops/status_summary.md`

## Self-Test

```bash
python3 scripts/phase_b_refresh_selftest.py
```
