# Mempool Listener Runbook

Provider-only listener:

```bash
source .env.local

python3 scripts/mempool_listener.py \
  --max-pending 25 \
  --timeout 60 \
  --out ops/reports/mempool-listener.latest.json
```

The listener subscribes to:

- `newPendingTransactions`;
- `newHeads`;
- target protocol `logs` from `config/protocol_log_addresses.json`.

It writes provider-only `PendingTxEvent` replay records under:

```text
data/replay/pending-tx.v1/
```

Provider-only limitations:

- `raw_tx` is unavailable from standard provider pending hash streams;
- `replacement_status` remains `unknown` without local txpool access.

