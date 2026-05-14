# Required Inputs Runbook

## Purpose

Check whether the user-provided inputs needed to leave provider-only shadow mode are present.

## Steps

1. Copy the contacts template:

```bash
cp config/ops_contacts.example.json config/ops_contacts.local.json
```

2. Fill in all `TBD` fields in `config/ops_contacts.local.json`.

3. Export trace endpoint and contacts config:

```bash
export ETH_MAIN_HTTP_URL="https://your-geth-or-erigon-trace-endpoint"
export OPS_CONTACTS_CONFIG="config/ops_contacts.local.json"
```

4. Run:

```bash
python3 scripts/required_inputs_check.py \
  --contacts "$OPS_CONTACTS_CONFIG" \
  --out ops/reports/required-inputs-check.latest.json
```
