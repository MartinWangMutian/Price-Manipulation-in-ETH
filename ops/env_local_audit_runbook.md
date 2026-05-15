# Env Local Audit Runbook

## Purpose

Check `.env.local` without writing endpoint secrets into reports.

The audit records only whether expected environment variables are present,
whether URL schemes look valid, and the endpoint host. URL paths and API keys are
redacted.

## Command

```bash
python3 scripts/env_local_audit.py \
  --env-file .env.local \
  --out ops/reports/env-local-audit.latest.json
```

## Self-Test

```bash
python3 scripts/env_local_audit_selftest.py
```

## Expected Current State

With only Alchemy provider fallback configured, the expected status is
`provider_configured_main_missing`. Phase B still needs a provider trace probe or
a dedicated `ETH_MAIN_HTTP_URL`.
