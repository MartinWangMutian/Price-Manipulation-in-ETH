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

## Provider-only note

Current provider-only graphs contain no transfer, call, or context edges. The checker validates the empty tx-only graph path now and will enforce edge semantics automatically once real trace edges are present.
