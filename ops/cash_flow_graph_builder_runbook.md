# Cash-flow Graph Builder Runbook

## Purpose

Phase 3-C builder that creates `graph-inference.v1` `GraphInferenceRequest` records from parsed trace and protocol role feature replay data.

## Inputs

- `data/replay/parsed-trace.v1/**.json`
- `data/replay/protocol-features.v1/**.json`

## Commands

Run the synthetic graph self-test:

```bash
python3 scripts/cash_flow_graph_builder_selftest.py
```

Build current replay graphs and snapshots:

```bash
python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --write-replay \
  --write-snapshot \
  --out ops/reports/cash-flow-graph-builder.latest.json
```

Validate written graph replay files independently:

```bash
python3 scripts/graph_replay_check.py \
  --input data/replay/graph-inference.v1 \
  --out ops/reports/graph-replay-check.latest.json
```

## Provider-only note

Provider fallback records do not include real calls or transfer logs. The expected provider-only graph is still valid but contains only the transaction node, `tx-only` context, and explicit missing-feature flags.
