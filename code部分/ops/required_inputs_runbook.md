# Required Inputs Runbook

## Purpose

Check whether the user-provided inputs and Phase B readiness gates needed to leave provider-only shadow mode are present.

## Steps

1. Bootstrap the local contacts file:

```bash
python3 scripts/ops_contacts_bootstrap.py \
  --report ops/reports/ops-contacts-bootstrap.latest.json
```

`config/ops_contacts.local.json` is ignored by git and should contain local
operational contact details only. The bootstrap command does not overwrite an
existing local contacts file unless `--force` is used.

2. Fill in all `TBD` fields in `config/ops_contacts.local.json`.

3. Export trace endpoint and contacts config:

```bash
export ETH_MAIN_HTTP_URL="https://your-geth-or-erigon-trace-endpoint"
export OPS_CONTACTS_CONFIG="config/ops_contacts.local.json"
```

4. Run the required input check:

```bash
python3 scripts/required_inputs_check.py \
  --contacts "$OPS_CONTACTS_CONFIG" \
  --out ops/reports/required-inputs-check.latest.json
```

5. Optional: if `ETH_PROVIDER_HTTP_URL` is already configured, test whether that
   provider can satisfy historical trace replay:

```bash
source .env.local
python3 scripts/trace_endpoint_preflight.py \
  --rpc-url "$ETH_PROVIDER_HTTP_URL" \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json
```

If this returns `status=ok`, set `ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"`
for the next steps. If it returns `degraded`, apply for or configure a dedicated
Geth/Erigon trace-capable endpoint.

6. After `ETH_MAIN_HTTP_URL` is available, run trace endpoint preflight:

```bash
python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

7. Refresh label readiness and rerun the required input check:

```bash
python3 scripts/label_readiness_audit.py \
  --out ops/reports/label-readiness-audit.latest.json

python3 scripts/required_inputs_check.py \
  --contacts "$OPS_CONTACTS_CONFIG" \
  --out ops/reports/required-inputs-check.latest.json
```

`missing_user_inputs` are values the user must provide. `readiness_gaps` are project checks or reports that must pass before the trace replay and label promotion path can continue.

## Self-Test

```bash
python3 scripts/required_inputs_check_selftest.py
```
