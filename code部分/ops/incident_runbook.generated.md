# Generated Incident Runbook

Generated at: 2026-05-14T04:44:26.947+00:00

## Provider-only Failure Posture

- Primary node failure: degrade to provider fallback if provider is available.
- Backup node failure: continue provider fallback.
- Provider unavailable: provider-only mode has no hot-path source; page engineer and pause live claims.
- Trace timeout or unsupported trace: continue graph/risk/alert with `trace_unsupported` and audit the degraded evidence.
- RAG timeout: emit alert first, then append `rag-explanation.v1` timeout explanation.
- Model mismatch or unavailable model: use rule baseline fallback and record `model_reject_reason`.
- Duplicate message delivery: rely on stage idempotency keys and replay checks.

## Current Drill Result

- status: ok
- duplicate alert idempotency keys: 0
- auditable degradation reason count: 880
