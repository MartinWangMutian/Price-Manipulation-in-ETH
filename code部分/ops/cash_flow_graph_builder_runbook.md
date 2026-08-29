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

For a paid replay batch, scope every input to the same `dt=...` partition and pass the batch-specific address/protocol context files. This prevents older provider-fallback records from being mixed into rich graphs.

Validate written graph replay files independently:

```bash
python3 scripts/graph_replay_check.py \
  --input data/replay/graph-inference.v1 \
  --out ops/reports/graph-replay-check.latest.json
```

## Rich graph lineage

Rich graph records include a `lineage` object linking the raw transaction, trace bundle, local raw trace, parsed trace, protocol-role feature record, and all three implementation versions. Successful `CREATE` and `CREATE2` traces use `result.address` as the call-edge destination.

## Provider-only note

Provider fallback records do not include real calls or transfer logs. The expected provider-only graph is still valid but contains only the transaction node, `tx-only` context, and explicit missing-feature flags.
