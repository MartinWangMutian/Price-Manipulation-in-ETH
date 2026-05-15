# Project Status Summary

Generated: 2026-05-15T08:05:02.758+00:00

Handoff: ops/phase_b_handoff.md
User action packet: ops/phase_b_user_action_packet.md
Completion checklist: ops/phase_b_completion_checklist.md

## Current Readiness

- Provider-only shadow pipeline: ok
- Production go/no-go: no_go
- Validation metrics: not_pass
- Required inputs: missing_inputs
- Env local: provider_configured_main_missing
- Provider trace probe: degraded
- Report secret audit: ok
- Phase B completion: blocked_user_input
- Phase B next action: apply_for_trace_endpoint
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

- live_trace_endpoint: Geth or Erigon trace HTTP endpoint (owner: user)
- ops_contacts: Pager/Feishu, phone/manual escalation, on-call, protocol partner, and approver names (owner: user)
- labeled_replay_sets: trace-replayed and analyst-promoted exploit and normal transaction labels (owner: project)
- live_failover_drill: primary/backup/provider switch test with real endpoints (owner: project)

## Go/No-Go Failures

- high_critical_graph_evidence
- high_critical_reason_codes
- high_critical_audit_log
- primary_node_switch_drill
- backup_node_switch_drill
- third_party_provider_switch_drill

## Metric Gaps

- roc_auc: GraphSAGE training is blocked
- pr_auc_lift: GraphSAGE training is blocked
- recall_at_fpr_3pct: GraphSAGE training is blocked
- lead_time: requires labeled attack timeline
- calibration_error: requires labeled validation set
- pending_enqueue_p95: live stream load test required
- trace_p95: Geth/Erigon trace endpoint required
- end_to_end_detection_p95: current value is replay timestamp gap, not live SLO

## Phase B Completion Audit

- Complete: False
- Missing checks: trace_endpoint_preflight_ok, historical_trace_replay_complete, label_promotion_complete, training_ready, ops_contacts_configured
- User blockers: trace_endpoint_preflight_ok, label_promotion_complete, ops_contacts_configured
- Project blockers: historical_trace_replay_complete, training_ready

## Env Local Audit

- Provider ready: True
- Main trace ready: False

## Provider Trace Probe

- Latest status: degraded
- Dry-run plan: ready_to_probe
- Provider host: eth-mainnet.g.alchemy.com

## Main Trace Endpoint Plan

- Dry-run plan: missing_or_invalid_main_trace_http_url
- ETH_MAIN_HTTP_URL present: False
- ETH_MAIN_HTTP_URL ok: False

## Report Secret Audit

- Scanned files: 67
- Findings: 0

## Ops Contacts Bootstrap

- Status: exists
- Local file git-ignored: True
- Next action: fill all TBD fields in config/ops_contacts.local.json

## Phase B Next Action

- Action: apply_for_trace_endpoint
- Owner: user
- Reason: Provider RPC is not sufficient for historical trace replay.

## Training Label Backlog

- Candidate transaction incidents: 7
- Candidate transactions: 7
- Missing Ethereum candidate incidents: none
- Normal complex set: candidate_queue_seeded_pending_trace (50 required)
- Historical trace replay queue: 7 items
- Trace endpoint preflight: missing_endpoint
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

## Inputs Needed From User

- ETH_MAIN_HTTP_URL: Geth/Erigon trace replay, trace P95, rich graph evidence (source: environment)
- pager_or_feishu_target: gray launch readiness, high/critical escalation (source: config/ops_contacts.local.json)
- phone_or_manual_escalation_target: manual escalation path, production go/no-go (source: config/ops_contacts.local.json)
- on_call_analyst: operational handoff, analyst review (source: config/ops_contacts.local.json)
- on_call_engineer: trace/model/infra validation (source: config/ops_contacts.local.json)
- incident_commander: critical incident coordination (source: config/ops_contacts.local.json)
- protocol_owner_or_partner_contact: protocol escalation, partner notification (source: config/ops_contacts.local.json)
- multisig_signer_or_authorized_approver: approval-gated suggested actions (source: config/ops_contacts.local.json)

## Phase B Readiness Gaps

- trace_endpoint_preflight: observed=missing_endpoint, real trace replay, trace P95, rich graph evidence (source: ops/reports/trace-endpoint-preflight.latest.json)

## Artifact Counts

- config: 14
- console: 112
- evaluation: 2
- rag: 2
- replay: 1015
- reports: 67
- runbooks_and_reports_docs: 79
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

# Optional: test whether ETH_PROVIDER_HTTP_URL can satisfy historical trace replay.
python3 scripts/provider_trace_capability_probe.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json

# Standard Phase B trace endpoint preflight; requires ETH_MAIN_HTTP_URL.
python3 scripts/main_trace_endpoint_preflight.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json

python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/historical-trace-replay.latest.json

python3 scripts/historical_trace_replay.py \
  --queue data/training/normal_trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/normal-historical-trace-replay.latest.json

python3 scripts/label_readiness_audit.py \
  --out ops/reports/label-readiness-audit.latest.json

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
