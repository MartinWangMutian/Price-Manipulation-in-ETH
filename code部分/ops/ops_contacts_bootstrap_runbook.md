# Ops Contacts Bootstrap Runbook

## Purpose

Create `config/ops_contacts.local.json` from the checked-in example without
committing local contact details.

## Command

```bash
python3 scripts/ops_contacts_bootstrap.py \
  --report ops/reports/ops-contacts-bootstrap.latest.json
```

The command does not overwrite an existing local contacts file unless `--force`
is passed. It also verifies that `config/ops_contacts.local.json` is ignored by
git.

## After Bootstrap

Fill every `TBD` field in `config/ops_contacts.local.json`, then export:

```bash
export OPS_CONTACTS_CONFIG="config/ops_contacts.local.json"
```

## Self-Test

```bash
python3 scripts/ops_contacts_bootstrap_selftest.py
```
