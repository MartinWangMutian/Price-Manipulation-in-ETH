# Project Status Summary

Generated: 2026-05-15T13:57:57.640+00:00

Handoff: ops/phase_b_handoff.md
User action packet: ops/phase_b_user_action_packet.md
Completion checklist: ops/phase_b_completion_checklist.md

## Current Readiness

- Scope mode: course_no_trace
- Trace replay required: False
- Provider-only shadow pipeline: ok
- Production go/no-go: no_go (out of scope)
- Validation metrics: not_pass (out of scope)
- Required inputs: ok
- Env local: provider_configured_main_missing
- Provider trace probe: degraded
- Report secret audit: ok
- Phase B completion: complete
- Phase B next action: none_phase_b_lite_complete
- Gray launch readiness: not_ready

## Passing Local Replay Surface

- pending_replay: ok
- trace_audit: ok
- graph_replay: ok
- risk_replay: ok
- alert_replay: ok
- rag_explanation: ok
- console_view: ok
- offline_eval: ok
- failure_drill: ok

## Blocking Items

- none recorded

## Out-Of-Scope Production Gaps

- Production go/no-go failures are retained for reference only and are waived for course_no_trace scope.

## Out-Of-Scope Metric Gaps

- Training/live-SLO metric gaps are retained for reference only and are waived for course_no_trace scope.

## Phase B Completion Audit

- Complete: True

## Env Local Audit

- Provider ready: True
- Main trace ready: False

## Provider Trace Probe

- Latest status: degraded
- Dry-run plan: ready_to_probe
- Provider host: eth-mainnet.g.alchemy.com

## Main Trace Endpoint Plan

- Scope: waived for course_no_trace
- Dry-run plan: missing_or_invalid_main_trace_http_url
- ETH_MAIN_HTTP_URL present: False
- ETH_MAIN_HTTP_URL ok: False

## Report Secret Audit

- Scanned files: 67
- Findings: 0

## Ops Contacts Bootstrap

- Status: exists
- Local file git-ignored: True
- Scope: optional for course_no_trace

## Phase B Next Action

- Action: none_phase_b_lite_complete
- Owner: none
- Reason: Course no-trace Phase B completion audit is complete; paid trace APIs and local nodes are waived by scope policy.

## Training Label Backlog

- Scope note: trace replay, trace-backed promotion, and training readiness are waived for this course assignment.
- Candidate transaction incidents: 7
- Candidate transactions: 7
- Missing Ethereum candidate incidents: none
- Normal complex set: candidate_queue_seeded_pending_trace (50 required)
- Historical trace replay queue: 7 items
- Trace endpoint preflight: degraded
- Historical exploit replay status: dry_run_ok
- Historical exploit replay persisted: 0 (ok=0, failed=0)
- Normal candidate transactions: 50
- Normal candidate check: ok
- Normal candidate buckets: contract_call=16, erc20_approve=3, erc20_transfer=16, simple_transfer=15
- Normal trace replay status: dry_run_ok
- Normal trace replay persisted: 0 (ok=0, failed=0)
- Historical trace results: awaiting_real_replay
- Persisted trace bundles: 0 / 57
- Label queue readiness: trace_ready
- Total trace queue items: 57
- Pending promotion decisions: 57
- Promoted labels: 0
- Training dataset check: ok
- Training ready: False

## Artifact Counts

- config: 15
- console: 112
- evaluation: 2
- rag: 2
- replay: 1015
- reports: 67
- runbooks_and_reports_docs: 80
- schemas: 7
- scripts: 74
- training: 11

## Next Commands

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json

python3 scripts/ops_contacts_bootstrap.py \
  --report ops/reports/ops-contacts-bootstrap.latest.json

python3 scripts/required_inputs_check.py \
  --contacts "${OPS_CONTACTS_CONFIG:-config/ops_contacts.local.json}" \
  --out ops/reports/required-inputs-check.latest.json

python3 scripts/env_local_audit.py \
  --env-file .env.local \
  --out ops/reports/env-local-audit.latest.json

python3 scripts/report_secret_audit.py \
  --input ops/reports \
  --out ops/reports/report-secret-audit.latest.json

python3 scripts/project_status_audit.py \
  --out ops/reports/project-status.latest.json \
  --blockers ops/blocker_register.md

python3 scripts/phase_b_completion_audit.py \
  --out ops/reports/phase-b-completion-audit.latest.json

python3 scripts/phase_b_next_action.py \
  --out ops/reports/phase-b-next-action.latest.json

python3 scripts/status_summary.py \
  --out ops/status_summary.md
```
