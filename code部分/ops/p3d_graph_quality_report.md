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

Provider-only replay checked 110 graphs with no errors. Current graph build latency is `p95=0.008ms`, below the Phase 3 target of 300ms.

## Remaining Validation Gap

Historical complex transaction comparison, real transfer/call edge inspection, and manual review of 10 rich cash-flow graphs still require real Geth or Erigon traces. Provider-only graphs are structurally valid but do not provide enough evidence for the full Phase 3 gate.
