# Phase B User Action Packet

## Current Blocker

Phase B is blocked by user-provided inputs, not by local code:

- Provider fallback is configured and passes local env shape checks.
- Provider trace probe has run and is degraded on the current Alchemy Free tier endpoint.
- Main trace endpoint is not configured.
- Operations contacts are still placeholders.
- Generated reports currently have no detected RPC key leakage.

## Action 1: Apply For Trace Endpoint

The current Alchemy Free tier endpoint passes normal Ethereum RPC checks but
rejects both `debug_traceTransaction` and `trace_transaction`.

Apply for, upgrade, or configure an Ethereum mainnet Geth/Erigon HTTP endpoint
that supports one of:

- `debug_traceTransaction`
- `trace_transaction`

Then set:

```bash
export ETH_MAIN_HTTP_URL="https://your-trace-capable-mainnet-endpoint"
```

## Action 2: Fill Operations Contacts

Create local contacts config:

```bash
python3 scripts/ops_contacts_bootstrap.py \
  --report ops/reports/ops-contacts-bootstrap.latest.json
```

`config/ops_contacts.local.json` is ignored by git so local contact details are
not committed. The bootstrap command will not overwrite an existing local file
unless you pass `--force`.

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
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

Or run the individual commands:

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
