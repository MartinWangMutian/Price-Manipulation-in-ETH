# Report Secret Audit Runbook

## Purpose

Scan generated JSON reports for accidental RPC endpoint secret leakage.

This is especially important after provider or trace endpoint probes. Reports
should contain redacted host/scheme metadata, not full `/v2/<key>` URLs.

## Command

```bash
python3 scripts/report_secret_audit.py \
  --input ops/reports \
  --out ops/reports/report-secret-audit.latest.json
```

## Self-Test

```bash
python3 scripts/report_secret_audit_selftest.py
```
