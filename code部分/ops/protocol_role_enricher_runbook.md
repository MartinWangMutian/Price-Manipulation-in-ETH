# Protocol Role Enricher Runbook

## Purpose

Phase 3-B role annotation for parsed trace features. It maps addresses observed in calls and transfers to whitelisted protocol roles, then writes `protocol-features.v1` replay records for the graph builder.

## Inputs

- `data/replay/parsed-trace.v1/**.json`
- `config/protocol_roles.json`

## Commands

Run the synthetic role matching self-test:

```bash
python3 scripts/protocol_role_enricher_selftest.py
```

Annotate current parsed replay records:

```bash
python3 scripts/protocol_role_enricher.py \
  --input data/replay/parsed-trace.v1 \
  --write-replay \
  --out ops/reports/protocol-role-enricher.latest.json
```

## Provider-only note

Provider fallback parsed traces do not contain calls or transfer logs, so the expected provider-only output has zero protocol role matches and the feature flags `no_protocol_role_matches` and `insufficient_trace_context_for_protocol_roles`.
