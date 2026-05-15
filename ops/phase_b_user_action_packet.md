# Phase B User Action Packet

## Current Blocker

Phase B is blocked by user-provided inputs, not by local code:

- Provider fallback is configured and passes local env shape checks.
- Provider trace probe dry-run is ready.
- Main trace endpoint is not configured.
- Operations contacts are still placeholders.
- Generated reports currently have no detected RPC key leakage.

## Action 1: Run Provider Trace Probe

Run this from the project root:

```bash
python3 scripts/provider_trace_capability_probe.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json
```

Then run:

```bash
python3 scripts/report_secret_audit.py \
  --input ops/reports \
  --out ops/reports/report-secret-audit.latest.json
```

Interpretation:

- If provider probe returns `status=ok` with `selected_method`, set
  `ETH_MAIN_HTTP_URL` to the provider HTTP URL for the next Phase B replay.
- If provider probe returns `degraded`, apply for or configure a dedicated
  Ethereum mainnet Geth/Erigon HTTP endpoint supporting `debug_traceTransaction`
  or `trace_transaction`.

## Action 2: Fill Operations Contacts

Create local contacts config:

```bash
cp config/ops_contacts.example.json config/ops_contacts.local.json
```

`config/ops_contacts.local.json` is ignored by git so local contact details are
not committed.

Fill every placeholder:

- `pager_or_feishu_target`
- `phone_or_manual_escalation_target`
- `on_call_analyst`
- `on_call_engineer`
- `incident_commander`
- `protocol_owner_or_partner_contact`
- `multisig_signer_or_authorized_approver`

Then export:

```bash
export OPS_CONTACTS_CONFIG="config/ops_contacts.local.json"
```

## Action 3: Refresh Gates

After Action 1 and Action 2:

```bash
python3 scripts/required_inputs_check.py \
  --contacts "$OPS_CONTACTS_CONFIG" \
  --out ops/reports/required-inputs-check.latest.json

python3 scripts/phase_b_completion_audit.py \
  --out ops/reports/phase-b-completion-audit.latest.json

python3 scripts/status_summary.py \
  --out ops/status_summary.md
```

Send the provider trace probe output before running historical replay.
