# Graph Quality Check Runbook

## Purpose

Phase 3-D automatic graph QA for `graph-inference.v1` replay records.

## Command

```bash
python3 scripts/graph_quality_check.py \
  --input data/replay/graph-inference.v1 \
  --builder-report ops/reports/cash-flow-graph-builder.latest.json \
  --out ops/reports/graph-quality-check.latest.json
```

## Checks

- Exactly one transaction node per graph
- Node id prefix matches node type
- Transfer edge endpoints point from address to address and reference an existing asset node when present
- Call edge endpoints point from address to address and call depth is non-negative when present
- Context edge points from address to protocol
- Graph build latency is copied from the builder report

For paid historical rich graphs, also run `scripts/rich_graph_quality_audit.py`. It requires exact queue coverage, `trace_transaction`, non-empty calls, raw-trace hash and lineage resolution, Call/Transfer count preservation, non-dangling references, snapshot equality, implementation versions, and the 7-attack plus 10-normal structural review set.

## Current rich-graph result

The 2026-08-29 paid replay partition contains 57 valid graphs with 11,521 Call edges, 492 Transfer edges, and 48 Context edges. The strict audit has zero errors. It records warnings for context cohort skew and low protocol-role dictionary coverage; these warnings must remain visible during label promotion and ablation design.

## Provider-only note

Current provider-only graphs contain no transfer, call, or context edges. The checker validates the empty tx-only graph path now and will enforce edge semantics automatically once real trace edges are present.
