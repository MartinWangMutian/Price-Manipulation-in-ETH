# Phase 1 Provider-only Development Runbook

**Mode:** provider-only development  
**Provider:** Alchemy or compatible Ethereum Mainnet RPC provider

## Purpose

Use this mode when local Ethereum Mainnet nodes are not available because of
disk or hardware constraints. It lets the project continue developing:

- WebSocket `newHeads` intake;
- provider pending transaction stream;
- target protocol log subscriptions;
- event schema validation;
- replay report generation.

This mode does not fully satisfy the Phase 1 Gate because it lacks local
`txpool`, peer health, and unrestricted Geth/Erigon trace paths.

## Required Environment

```bash
export ETH_PROVIDER_HTTP_URL="<alchemy https endpoint>"
export ETH_PROVIDER_WS_URL="<alchemy wss endpoint>"
```

If Python certificate validation fails on macOS or Anaconda:

```bash
export SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')"
```

## 1. Health Check

```bash
python3 scripts/node_health_check.py \
  --config config/rpc_endpoints.example.json \
  --out ops/reports/node-health.latest.json
```

Provider-only success means:

- `active_endpoint_recommendation = provider-pending-fallback`;
- provider `chain_id.ok = true`;
- provider `head.ok = true`;
- provider `websocket_new_heads.ok = true`.

`txpool_api`, `peer_count`, and provider trace checks are skipped for provider
fallback endpoints to avoid unnecessary Alchemy CU usage. This is expected.

## 2. WebSocket Smoke Test

```bash
python3 scripts/provider_smoke_test.py \
  --subscription-min-interval-ms 200 \
  --out ops/reports/provider-smoke.latest.json
```

The smoke test verifies subscription establishment for:

- `newHeads`;
- `newPendingTransactions`;
- `logs` for `config/protocol_log_addresses.json`.

It also captures a small pending transaction sample when the provider emits
pending transaction hashes within the timeout.

## 3. Pending Listener With Low Peak Throughput

Alchemy peak throughput is CU/s based, so avoid bursts even for short runs. The
pending listener defaults to 5 HTTP RPC calls per second with a 200 ms minimum
gap between transaction fetches:

```bash
python3 scripts/provider_pending_listener.py \
  --max-events 10 \
  --http-max-rps 5 \
  --http-min-interval-ms 200 \
  --summary-out ops/reports/pending-listener.latest.json
```

For very conservative runs under a 500 CU/s peak limit:

```bash
python3 scripts/provider_pending_listener.py \
  --max-events 10 \
  --http-max-rps 1 \
  --http-min-interval-ms 1000 \
  --summary-out ops/reports/pending-listener.latest.json
```

## 4. Completion Boundary

After both reports pass, mark only the provider fallback intake item complete.
Do not mark local node deployment, Geth `debug_traceCall`, Erigon `trace_call`,
or the Phase 1 Gate complete until real local or remote dedicated nodes are
available.
