# P3-B Protocol Roles Report

## Scope

Implemented the Phase 3-B protocol role table and offline role annotator used by the graph builder.

## Implemented

- Protocol contract role table for the Phase 0 whitelist
- Pool, router, oracle, lending market, liquidation module, and emergency surface role tags
- Dynamic Uniswap v3 pool role rule for future `Factory.getPool(token0,token1,fee)` expansion
- Parsed trace role annotation for call addresses and transfer token/from/to/operator addresses
- `protocol-features.v1` replay output for graph feature consumption

## Current Validation

Synthetic self-test covers lending market, liquidation module, and oracle role matching.

Provider-only parsed replay has no calls or transfers. The role enricher loaded 10 whitelisted role contracts and wrote 110 `protocol-features.v1` records.

Expected provider-only result:

- `records_with_role_matches`: 0
- `role_counts`: empty
- `protocol_counts`: empty
- `feature_missing_flags`: `trace_unsupported`, `no_logs`, `no_calls`, `no_protocol_role_matches`, `insufficient_trace_context_for_protocol_roles`
- `errors`: empty

## Remaining Runtime Gap

Role matching quality depends on real parsed call and transfer evidence from Geth or Erigon traces. Dynamic pool expansion still needs a live RPC lookup stage before exhaustive Uniswap v3 pool coverage.
