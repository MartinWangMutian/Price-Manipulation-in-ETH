# Phase B Handoff

## Current State

- Provider-only shadow pipeline: ok
- Label queue readiness: trace_ready
- Exploit trace queue: 7 transactions
- Normal trace queue: 50 transactions
- Historical trace results: awaiting_real_replay
- Persisted historical trace bundles: 0 / 57
- Training ready: false
- Env local: provider_configured_main_missing
- Provider trace probe: degraded; current Alchemy Free tier endpoint does not expose trace methods
- Report secret audit: ok
- Production go/no-go: no_go

## User Inputs Needed

For the shortest user-facing checklist, see
`ops/phase_b_user_action_packet.md`.
For the evidence checklist, see `ops/phase_b_completion_checklist.md`.
For endpoint upgrade details, see `ops/trace_endpoint_application_guide.md`.

1. `ETH_MAIN_HTTP_URL`
   - Must be an Ethereum mainnet Geth or Erigon HTTP endpoint.
   - Must support either `debug_traceTransaction` or `trace_transaction`.
   - Current Alchemy Free tier provider endpoint is useful for pending/provider shadow mode, but it does not satisfy this trace requirement.

2. Operations contact config
   - Run `python3 scripts/ops_contacts_bootstrap.py --report ops/reports/ops-contacts-bootstrap.latest.json`.
   - `config/ops_contacts.local.json` is ignored by git.
   - Fill pager or Feishu target, phone/manual escalation, on-call analyst, on-call engineer, incident commander, protocol owner or partner contact, and authorized approver.
   - Export `OPS_CONTACTS_CONFIG=config/ops_contacts.local.json`.

## Current Safe Prechecks

Run these any time after editing `.env.local` or generated reports:

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

For a narrower check, run the individual audits:

```bash
python3 scripts/env_local_audit.py \
  --env-file .env.local \
  --out ops/reports/env-local-audit.latest.json

python3 scripts/report_secret_audit.py \
  --input ops/reports \
  --out ops/reports/report-secret-audit.latest.json
```

The env audit redacts URL paths and API keys. The report secret audit should
return `status=ok` before sharing generated reports.

## Endpoint Validation

Run this first after `ETH_MAIN_HTTP_URL` is configured:

```bash
source .env.local
python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

Proceed only if `status=ok`. The report will show `selected_method`.

## Optional Provider Probe

The current `.env.local` has a valid provider HTTP URL shape. To test whether it
can also serve as the historical trace endpoint, run:

```bash
python3 scripts/provider_trace_capability_probe.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json
```

Only use it for Phase B replay if the probe returns `status=ok` with a
`selected_method`. After the probe, rerun `report_secret_audit.py`.

## Historical Replay

```bash
python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/historical-trace-replay.latest.json

python3 scripts/historical_trace_replay.py \
  --queue data/training/normal_trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/normal-historical-trace-replay.latest.json

python3 scripts/historical_trace_results_audit.py \
  --out ops/reports/historical-trace-results-audit.latest.json
```

`historical_trace_replay.py` writes only successful trace bundles by default.
Failed attempts stay in the report and do not pollute replay storage.

## After Replay

```bash
python3 scripts/trace_parser.py \
  --input data/replay/trace-bundle.v1 \
  --write-replay \
  --out ops/reports/trace-parser.latest.json

python3 scripts/protocol_role_enricher.py \
  --input data/replay/parsed-trace.v1 \
  --write-replay \
  --out ops/reports/protocol-role-enricher.latest.json

python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --write-replay \
  --write-snapshot \
  --out ops/reports/cash-flow-graph-builder.latest.json
```

## Still Not Automatic

Do not mark labels training-ready until `data/training/label_promotion_decisions.seed.json`
has analyst-reviewed promoted decisions with trace and graph references.
