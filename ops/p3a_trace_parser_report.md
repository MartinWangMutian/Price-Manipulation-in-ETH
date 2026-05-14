# P3-A Trace Parser Report

## Scope

Implemented the Phase 3-A parser for normalized transfer and call extraction from `trace-bundle.v1` replay records.

## Implemented

- ERC-20 `Transfer(address,address,uint256)` parsing
- ERC-721 `Transfer(address,address,uint256)` parsing when token metadata marks the contract as `erc721` or the event uses the indexed token id shape
- ERC-1155 `TransferSingle` and `TransferBatch` parsing
- `amount_raw`, `amount_norm`, and token decimal normalization through token metadata cache
- Call depth, call type, selector, success, and revert reason extraction for Geth and Erigon-shaped call entries
- Selector dictionary and token metadata cache bootstrap files
- Provider-only fallback handling with explicit `feature_missing_flags`

## Current Validation

Synthetic self-test passes for ERC-20, ERC-1155, selector extraction, call depth, call success, and revert reason parsing.

Current replay input is provider fallback only. The parser saw 220 trace bundle files, skipped 110 duplicate replay files by idempotency key, and wrote 110 parsed records to `data/replay/parsed-trace.v1`.

Expected provider-only result:

- `token_transfer_counts`: empty
- `calls.total`: 0
- `feature_missing_flags`: `trace_unsupported`, `no_logs`, `no_calls` on all 110 records
- `errors`: empty

## Remaining Runtime Gap

Real ERC transfer and call-tree evidence still requires a configured Geth or Erigon trace endpoint. Provider-only mode cannot supply raw call trees, logs inside pending traces, or replacement/drop status.
