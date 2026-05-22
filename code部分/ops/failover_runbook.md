# Phase 1 Node Failover Runbook

**Version:** `node-failover.v1`  
**Chain:** Ethereum Mainnet (`chain_id=1`)

## Endpoint Priority

1. `local-geth-primary`
2. `local-erigon-backup`
3. `provider-pending-fallback`

Local execution nodes remain the preferred source for pending transactions,
heads, logs, and trace/debug. Third-party providers are fallback and supplement
sources only.

## Health Signals

An endpoint is healthy when:

- `eth_chainId` returns `0x1`;
- `eth_blockNumber` is no more than 2 blocks behind the best observed endpoint;
- `net_peerCount` succeeds;
- trace/debug method availability succeeds;
- WebSocket `eth_subscribe` to `newHeads` succeeds.

`txpool_status` must be checked for local nodes. Provider endpoints may not
support txpool methods, so missing txpool is degraded rather than fatal for
provider fallback.

## Failover Rule

Switch from the active endpoint when any of these conditions lasts for more
than 60 seconds:

- HTTP RPC is unavailable;
- WebSocket `newHeads` subscription is unavailable;
- head lag is greater than 2 blocks;
- trace/debug method is unavailable;
- RPC latency P95 is above 500 ms over the last 5 minutes.

When switching:

1. record failing endpoint, first failure time, recovery time if known, and
   missing block or pending time range;
2. switch consumers to the next healthy endpoint by priority;
3. mark events produced during failover with `source` and
   `feature_missing_flags` where applicable;
4. replay from durable storage once the primary recovers.

## Report Command

```bash
ETH_MAIN_HTTP_URL=http://127.0.0.1:8545 \
ETH_MAIN_WS_URL=ws://127.0.0.1:8546 \
python3 scripts/node_health_check.py \
  --config config/rpc_endpoints.example.json \
  --out ops/reports/node-health.latest.json
```

The command exits with status `0` when at least one healthy endpoint is
available, otherwise status `2`.

