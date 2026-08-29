# P3-C Cash-flow Graph Builder Report

## Scope

Implemented the Phase 3-C cash-flow graph builder and serialization format for downstream `GraphInferenceRequest` inference.

## Implemented

- Address, Asset, Protocol, and Transaction nodes
- Transfer, Call, and Context edges
- `tx-only` graph construction
- Optional `5m-address` and `1h-protocol` context inputs
- Context timeout/unavailable fallback to `tx-only`
- `feature_missing_flags` propagation from parsed trace and protocol role features
- Replay output and graph snapshot output
- Graph serialization documentation

## Current Validation

Synthetic self-test covers non-empty transfer, call, protocol role, and context edges.

The paid 2026-08-29 replay partition built 57 rich `graph-inference.v1` records and 57 matching snapshots from `trace_transaction` bundles.

Current rich-graph result:

- `graphs_built`: 57
- `context_window_counts`: `tx-only=57`, `5m-address=18`
- `node_counts`: transaction=57, address=583, asset=96, protocol=1, context=34
- `edge_counts`: Call=11,521, Transfer=492, Context=48
- call depth maximum: 22
- build latency: `p95=1.017ms`, `max=19.536ms`
- independent graph replay check: `valid_graphs=57`, duplicate idempotency keys empty, errors empty
- every new graph contains raw transaction/trace, parsed-feature, role-feature, and implementation-version lineage

The parser now preserves `CREATE`/`CREATE2` calls by resolving the created contract from Parity `result.address`; all 11,521 parsed calls therefore have graph Call edges.

## Remaining Research Gap

These 57 graphs satisfy the Phase 3 engineering gate but remain too small for a research conclusion. Protocol-role coverage is 1/57 and must be expanded before research-grade training.
