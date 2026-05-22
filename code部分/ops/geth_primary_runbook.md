# Phase 1 Geth Primary Node Runbook

**Goal:** bring up `local-geth-primary` for Ethereum Mainnet and expose the
RPC capabilities required by Phase 1.

## Why This Is Needed

Alchemy is now usable as `provider-pending-fallback`, but Phase 1 still needs a
local execution node because provider endpoints usually do not expose `txpool`,
peer state, or unrestricted trace/debug namespaces.

Geth is an execution client. On Ethereum Mainnet it must run with a consensus
client, such as Lighthouse, Prysm, Teku, Nimbus, or Lodestar. Both clients share
a JWT secret for the authenticated engine API.

## Hardware Notes

Use a machine with enough disk and network capacity for Ethereum Mainnet. Do
not expose `debug`, `txpool`, or authenticated RPC ports to the public internet.
Bind RPC to `127.0.0.1` unless the node is behind a private network or VPN.

## 1. Install Clients

On macOS with Homebrew:

```bash
brew tap ethereum/ethereum
brew install ethereum
brew install lighthouse
```

If `lighthouse` is unavailable in your Homebrew setup, use another consensus
client or install Lighthouse from its official release instructions.

Verify:

```bash
geth version
lighthouse --version
```

## 2. Create Data Directories and JWT Secret

```bash
mkdir -p "$HOME/eth-mainnet/geth" "$HOME/eth-mainnet/lighthouse"
openssl rand -hex 32 > "$HOME/eth-mainnet/jwt.hex"
chmod 600 "$HOME/eth-mainnet/jwt.hex"
```

## 3. Start Geth

```bash
geth \
  --mainnet \
  --datadir "$HOME/eth-mainnet/geth" \
  --http \
  --http.addr 127.0.0.1 \
  --http.port 8545 \
  --http.api eth,net,web3,txpool,debug \
  --ws \
  --ws.addr 127.0.0.1 \
  --ws.port 8546 \
  --ws.api eth,net,web3,txpool,debug \
  --authrpc.addr 127.0.0.1 \
  --authrpc.port 8551 \
  --authrpc.vhosts localhost \
  --authrpc.jwtsecret "$HOME/eth-mainnet/jwt.hex"
```

Keep this terminal running.

## 4. Start Lighthouse Beacon Node

Open a second terminal:

```bash
lighthouse bn \
  --network mainnet \
  --datadir "$HOME/eth-mainnet/lighthouse" \
  --execution-endpoint http://127.0.0.1:8551 \
  --execution-jwt "$HOME/eth-mainnet/jwt.hex" \
  --checkpoint-sync-url https://mainnet.checkpoint.sigp.io
```

Keep this terminal running.

## 5. Export Project Environment Variables

Open a third terminal in the project directory:

```bash
export ETH_MAIN_HTTP_URL="http://127.0.0.1:8545"
export ETH_MAIN_WS_URL="ws://127.0.0.1:8546"
```

Keep the Alchemy provider variables in the same terminal:

```bash
export ETH_PROVIDER_HTTP_URL="<alchemy https endpoint>"
export ETH_PROVIDER_WS_URL="<alchemy wss endpoint>"
```

## 6. Validate Geth RPC

```bash
python3 scripts/node_health_check.py \
  --config config/rpc_endpoints.example.json \
  --out ops/reports/node-health.latest.json
```

Expected result for `local-geth-primary` after sync has progressed:

- `chain_id.ok = true`
- `head.ok = true`
- `peer_count.ok = true`
- `txpool_api.ok = true`
- `trace_api.ok = true`
- `websocket_new_heads.ok = true`

If the node is still syncing, `head_lag` may be high. That is not a script
failure; wait for sync to catch up before marking Phase 1 node deployment done.

## 7. Manual RPC Spot Checks

```bash
curl -s -X POST "$ETH_MAIN_HTTP_URL" \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}'
```

```bash
curl -s -X POST "$ETH_MAIN_HTTP_URL" \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"txpool_status","params":[],"id":1}'
```

```bash
curl -s -X POST "$ETH_MAIN_HTTP_URL" \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"debug_traceCall","params":[{"from":"0x0000000000000000000000000000000000000000","to":"0x0000000000000000000000000000000000000000","data":"0x"},"pending",{}],"id":1}'
```

## Completion Criteria

Mark the Geth-related Phase 1 items complete only after:

1. Geth and the consensus client are both running;
2. Geth is close enough to the canonical head to satisfy the head lag rule;
3. `node_health_check.py` reports `local-geth-primary` as `ok`;
4. `debug_traceCall` with `pending` is available.

