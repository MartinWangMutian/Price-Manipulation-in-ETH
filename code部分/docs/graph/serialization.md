# Cash-flow Graph Serialization

## Record

Graph records use `schema_ver=graph-inference.v1` and are written as `GraphInferenceRequest` JSON documents.

Required top-level fields:

- `graph_id`: stable transaction graph id, currently `graph:<tx_hash>`
- `tx_hash`: transaction hash
- `nodes`: graph node list
- `edges`: graph edge list
- `feature_ver`: graph builder implementation version
- `lineage`: transaction, trace bundle, raw trace, parsed trace, protocol feature, and implementation-version references
- `context_windows`: included context windows, always including `tx-only`
- `feature_missing_flags`: explicit missing or degraded feature flags

## Nodes

Node ids are stable strings:

- `tx:<tx_hash>` for the transaction node
- `address:<address>` for externally owned accounts or contracts observed in calls/transfers
- `asset:<token_address>` for transferred token contracts
- `protocol:<contract_address>` for whitelisted protocol contracts

## Edges

Edge types:

- `transfer`: value movement from sender address to receiver address, with `asset_node`, `amount_raw`, `amount_norm`, token id, and token standard when available
- `call`: EVM call from caller address to callee address, with depth, call type, selector, function name, success, and revert reason
- `call` also represents successful `CREATE`/`CREATE2`; the created address from `result.address` is the destination node
- `context`: annotation edge from an observed address to a protocol node, currently used for protocol-role context

## Context Windows

The builder must always be able to emit a `tx-only` graph. Optional context windows are:

- `5m-address`: recent address context if supplied by an external context file
- `1h-protocol`: recent protocol context if supplied by an external context file

If context is unavailable or times out, the graph remains valid and records a `feature_missing_flags` entry instead of blocking.

## Lineage

New rich graphs retain the logical transaction reference, source trace-bundle event/idempotency keys, local raw-trace reference, parsed-trace and protocol-feature event/idempotency keys, and the parser/enricher/builder versions. `rich_graph_quality_audit.py` resolves and compares these references before a graph can proceed to label review.
