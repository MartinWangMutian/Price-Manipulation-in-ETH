# P2-A Mempool Listener Report

**Report time:** 2026-05-14  
**Mode:** provider-only fallback validation

## Implemented

`scripts/mempool_listener.py` implements provider-only subscriptions for:

- `newPendingTransactions`;
- `newHeads`;
- target protocol `logs` from `config/protocol_log_addresses.json`.

Pending transaction hashes are fetched via `eth_getTransactionByHash`, converted
to `PendingTxEvent`, and persisted to replay storage.

## Validation Result

Latest listener run:

- subscriptions established: `logs`, `newHeads`, `newPendingTransactions`
- pending events written: `25`
- deduped pending hashes in run: `25`
- total pending replay files: `135`
- total valid pending replay events: `135`
- duplicate pending idempotency keys: `0`
- validation errors: `0`

Listener latency was measured in provider-only mode:

- P50 enqueue latency: `460.52 ms`
- P95 enqueue latency: `503.77 ms`
- max enqueue latency: `526.46 ms`

This latency includes provider HTTP transaction-object fetch and local file
write. It is not expected to meet the final `<=100 ms` hot-path intake target
until a local or dedicated txpool source is available.

## Provider-only Limitations

- `raw_tx` is unavailable from standard provider pending hash streams.
- `replacement_status` remains `unknown` without local txpool access.
- log subscriptions can be established, but log events only appear when target
  protocol contracts emit logs during the run window.

## Reports

- `ops/reports/mempool-listener.latest.json`
- `ops/reports/pending-replay-check-p2a.latest.json`

