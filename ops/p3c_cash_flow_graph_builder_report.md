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

Provider-only replay built 110 valid `graph-inference.v1` records and 110 graph snapshots.

Current provider-only result:

- `graphs_built`: 110
- `context_window_counts`: `tx-only=110`
- `node_counts`: `transaction=110`
- `edge_counts`: empty
- build latency: `p95=0.008ms`, `max=0.068ms`
- independent graph replay check: `valid_graphs=110`, duplicate idempotency keys empty, errors empty

Empty edges are expected because the current trace source is provider fallback and has no calls/logs.

## Remaining Runtime Gap

Graph quality and edge richness depend on real Geth or Erigon traces. Provider-only graphs are useful for pipeline continuity but do not satisfy the Phase 3 historical-complex-transaction validation gate.
