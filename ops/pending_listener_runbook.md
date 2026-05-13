# Provider-only Pending Listener Runbook

This runbook captures pending transaction hashes from the provider WebSocket,
fetches available transaction objects over HTTP, emits `PendingTxEvent`, and
writes replay records under `data/replay/pending-tx.v1/`.

## Run

```bash
python3 scripts/provider_pending_listener.py \
  --max-events 10 \
  --http-max-rps 5 \
  --http-min-interval-ms 200 \
  --summary-out ops/reports/pending-listener.latest.json
```

Required environment:

```bash
export ETH_PROVIDER_HTTP_URL="<alchemy https endpoint>"
export ETH_PROVIDER_WS_URL="<alchemy wss endpoint>"
```

## Throughput Guardrail

The listener defaults to at most 5 HTTP RPC calls per second and at least 200 ms
between `eth_getTransactionByHash` requests. For a 500 CU/s Alchemy peak limit,
keep this conservative unless the provider plan is upgraded.

To reduce peak throughput further:

```bash
python3 scripts/provider_pending_listener.py \
  --max-events 10 \
  --http-max-rps 1 \
  --http-min-interval-ms 1000 \
  --summary-out ops/reports/pending-listener.latest.json
```

## Provider-only Limitation

Standard provider pending subscriptions emit transaction hashes. The listener
uses `eth_getTransactionByHash` to fetch the transaction object. It does not
receive the raw signed transaction bytes, so provider-only events use:

```json
{
  "raw_tx": null,
  "raw_tx_status": "unavailable_from_provider"
}
```

When a local txpool-backed node is added, `raw_tx_status` should become
`available` for events where raw transaction bytes are captured.

## Output

Summary:

```text
ops/reports/pending-listener.latest.json
```

Replay records:

```text
data/replay/pending-tx.v1/dt=YYYY-MM-DD/hour=HH/<event_id>.json
```
