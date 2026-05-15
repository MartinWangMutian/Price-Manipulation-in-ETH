# Phase B Completion Checklist

Generated from current local reports on 2026-05-15.

## Objective

Continue Phase B until the trace-backed replay, label promotion, and training
readiness gates are complete, asking the user only for inputs that cannot be
created locally.

## Checklist

| Requirement | Evidence | Current status |
| --- | --- | --- |
| Provider-only shadow pipeline is healthy | `ops/reports/project-status.latest.json` via `provider_only_shadow_pipeline` | Pass: `ok` |
| Trace replay queues are ready | `ops/reports/label-readiness-audit.latest.json` | Pass: `trace_ready`, 57 queued items |
| Local provider/main env shape is audited without leaking keys | `ops/reports/env-local-audit.latest.json` | Partial: provider ready, main trace endpoint missing |
| Provider trace capability has been tested against the real provider | `ops/reports/provider-trace-capability-probe.latest.json` | Blocked: `degraded`; current Alchemy Free tier rejects both trace methods |
| Standard trace endpoint preflight passes | `ops/reports/trace-endpoint-preflight.latest.json` | Blocked: `missing_endpoint` |
| Exploit and normal historical trace replay bundles are persisted | `ops/reports/historical-trace-results-audit.latest.json` | Blocked: `awaiting_real_replay`, 0 / 57 persisted |
| Labels have analyst-promoted trace-backed decisions | `ops/reports/label-promotion-audit.latest.json` | Blocked: 57 pending trace decisions, 0 promoted |
| Training dataset is ready | `ops/reports/training-dataset-check.latest.json` | Blocked: `training_ready=false` |
| Operations contacts are filled locally and ignored by git | `config/ops_contacts.local.json`, `ops/reports/ops-contacts-bootstrap.latest.json`, `.gitignore` | Partial: file exists and is ignored, fields still `TBD` |
| Generated reports do not expose RPC URL secrets | `ops/reports/report-secret-audit.latest.json` | Pass: `ok`, 0 findings |
| Phase B handoff and next-action documents are present | `ops/phase_b_handoff.md`, `ops/phase_b_user_action_packet.md`, `ops/reports/phase-b-next-action.latest.json` | Pass: next action is `apply_for_trace_endpoint` |

## Current Blockers

1. Provide a trace-capable Ethereum mainnet HTTP endpoint. The current Alchemy
   Free tier endpoint passes `eth_chainId`, but rejects both
   `debug_traceTransaction` and `trace_transaction`.

2. Fill all `TBD` values in `config/ops_contacts.local.json`.

3. Refresh local gates:

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

## Completion Rule

Phase B is complete only when
`ops/reports/phase-b-completion-audit.latest.json` reports
`phase_b_complete=true`.
