# P3-D Graph Quality Report

## Scope

Added automatic graph quality checks for replayed `graph-inference.v1` records.

## Implemented Checks

- Node type and node id consistency
- Transfer edge direction and asset-node references
- Call edge direction and call depth shape
- Context edge address-to-protocol direction
- Graph build latency reporting

## Current Validation

The strict paid-replay audit checked all 57 expected graph lineages with no missing records, duplicates, provider fallback, unsupported traces, dangling references, edge-count loss, raw-trace hash mismatch, or snapshot mismatch. It reviewed all 7 attack graphs and a deterministic bucket-stratified sample of 10 normal graphs; all 17 passed structural review.

Current totals are 57 transaction nodes, 583 address nodes, 96 asset nodes, 1 protocol node, 34 context nodes, 11,521 Call edges, 492 Transfer edges, and 48 Context edges. Maximum call depth is 22. Graph build latency is `p95=1.017ms`.

## Non-blocking Warnings

- Five-minute address context coverage is 0% for attack candidates and 36% for normal candidates. Context features require explicit leakage checks and an ablation before training conclusions.
- The current protocol-role dictionary matches only one graph. Expand role coverage before research-grade data freezing.
- Labels remain candidates. Phase 3 completion does not authorize training until Phase 4 evidence review, promotion, and grouped split freezing are complete.
