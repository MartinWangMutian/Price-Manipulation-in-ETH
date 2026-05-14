#!/usr/bin/env python3
"""Provider-only mempool and protocol log listener.

Subscribes to pending transaction hashes, newHeads, and target protocol logs.
Pending transaction hashes are converted to PendingTxEvent replay records.
Heads and logs are sampled into the listener report for Phase 2-A validation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SSL_CONTEXT: ssl.SSLContext | None = None


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_dt().isoformat(timespec="milliseconds")


def ssl_context() -> ssl.SSLContext:
    global SSL_CONTEXT
    if SSL_CONTEXT is not None:
        return SSL_CONTEXT
    try:
        import certifi  # type: ignore[import-not-found]

        SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        SSL_CONTEXT = ssl.create_default_context()
    return SSL_CONTEXT


def ws_frame(payload: bytes) -> bytes:
    key = os.urandom(4)
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", 0x81, 0x80 | length)
    elif length < 65536:
        header = struct.pack("!BBH", 0x81, 0x80 | 126, length)
    else:
        header = struct.pack("!BBQ", 0x81, 0x80 | 127, length)
    masked = bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))
    return header + key + masked


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise OSError("websocket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_ws_payload(sock: socket.socket) -> bytes:
    header = recv_exact(sock, 2)
    first, second = header
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exact(sock, 8))[0]
    if second & 0x80:
        mask = recv_exact(sock, 4)
        payload = recv_exact(sock, length)
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    else:
        payload = recv_exact(sock, length)
    if opcode == 8:
        raise OSError("websocket close frame received")
    if opcode == 9:
        sock.sendall(ws_frame(payload))
        return read_ws_payload(sock)
    return payload


def connect_ws(url: str, timeout_s: float) -> socket.socket:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("missing websocket host")
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    raw_sock = socket.create_connection((host, port), timeout=timeout_s)
    sock = ssl_context().wrap_socket(raw_sock, server_hostname=host) if parsed.scheme == "wss" else raw_sock
    sock.settimeout(timeout_s)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(handshake.encode("ascii"))
    response = sock.recv(4096)
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise OSError("websocket upgrade failed")
    return sock


def send_rpc(sock: socket.socket, request_id: int, method: str, params: list[Any]) -> None:
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    sock.sendall(ws_frame(json.dumps(payload).encode("utf-8")))


def rpc_call(url: str, method: str, params: list[Any], timeout_s: float) -> dict[str, Any]:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_s, context=ssl_context()) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        try:
            return json.loads(exc.read())
        except json.JSONDecodeError:
            return {"error": f"HTTP {exc.code}: {exc.reason}"}
    except (URLError, TimeoutError, OSError) as exc:
        return {"error": str(exc)}


def event_id_for(chain_id: int, tx_hash: str, source: str) -> str:
    seed = f"pending-tx.v1:{chain_id}:{tx_hash}:{source}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def pending_replay_path(root: Path, created_at: datetime, event_id: str) -> Path:
    return (
        root
        / "data"
        / "replay"
        / "pending-tx.v1"
        / f"dt={created_at.strftime('%Y-%m-%d')}"
        / f"hour={created_at.strftime('%H')}"
        / f"{event_id}.json"
    )


def load_addresses(path: Path) -> list[str]:
    config = json.loads(path.read_text(encoding="utf-8"))
    return [item["address"] for item in config["addresses"]]


def build_pending_event(
    tx_hash: str,
    tx_response: dict[str, Any],
    source: str,
    chain_id: int,
    created: datetime,
    fetch_latency_ms: float,
) -> dict[str, Any]:
    tx = tx_response.get("result")
    if tx:
        raw_tx_status = "unavailable_from_provider"
    elif "error" in tx_response:
        raw_tx_status = "error"
    else:
        raw_tx_status = "not_found"
    event_id = event_id_for(chain_id, tx_hash, source)
    return {
        "event_id": event_id,
        "schema_ver": "pending-tx.v1",
        "chain_id": chain_id,
        "created_at": created.isoformat(timespec="milliseconds"),
        "idempotency_key": f"{chain_id}:{tx_hash}:{source}",
        "tx_hash": tx_hash,
        "raw_tx": None,
        "raw_tx_status": raw_tx_status,
        "tx": tx,
        "seen_at": created.isoformat(timespec="milliseconds"),
        "source": source,
        "replacement_status": "unknown",
        "fetch_latency_ms": round(fetch_latency_ms, 2),
    }


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(round((pct / 100) * (len(sorted_values) - 1))))
    return round(sorted_values[index], 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws-url-env", default="ETH_PROVIDER_WS_URL")
    parser.add_argument("--http-url-env", default="ETH_PROVIDER_HTTP_URL")
    parser.add_argument("--source", default="provider-pending-fallback")
    parser.add_argument("--chain-id", type=int, default=1)
    parser.add_argument("--max-pending", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--addresses", default="config/protocol_log_addresses.json")
    parser.add_argument("--out", default="ops/reports/mempool-listener.latest.json")
    args = parser.parse_args()

    ws_url = os.getenv(args.ws_url_env)
    http_url = os.getenv(args.http_url_env)
    if not ws_url:
        raise SystemExit(f"missing env {args.ws_url_env}")
    if not http_url:
        raise SystemExit(f"missing env {args.http_url_env}")

    root = Path(__file__).resolve().parents[1]
    addresses = load_addresses(root / args.addresses)
    started = time.monotonic()
    sock = connect_ws(ws_url, args.timeout)
    request_names = {1: "newHeads", 2: "newPendingTransactions", 3: "logs"}
    subscription_names: dict[str, str] = {}
    seen_hashes: set[str] = set()
    pending_events = []
    head_samples = []
    log_samples = []
    enqueue_latencies: list[float] = []
    errors = []

    try:
        send_rpc(sock, 1, "eth_subscribe", ["newHeads"])
        send_rpc(sock, 2, "eth_subscribe", ["newPendingTransactions"])
        send_rpc(sock, 3, "eth_subscribe", ["logs", {"address": addresses}])

        while time.monotonic() - started < args.timeout:
            try:
                message = json.loads(read_ws_payload(sock))
            except socket.timeout:
                continue

            received_at = time.perf_counter()
            if "id" in message:
                name = request_names.get(message["id"], f"request_{message['id']}")
                if "result" in message:
                    subscription_names[message["result"]] = name
                else:
                    errors.append({"subscription": name, "error": message.get("error")})
                continue

            params = message.get("params", {})
            name = subscription_names.get(params.get("subscription"))
            result = params.get("result")
            if name == "newHeads" and isinstance(result, dict):
                if len(head_samples) < 3:
                    head_samples.append(
                        {"number": result.get("number"), "hash": result.get("hash")}
                    )
            elif name == "logs" and isinstance(result, dict):
                if len(log_samples) < 5:
                    log_samples.append(
                        {
                            "address": result.get("address"),
                            "blockNumber": result.get("blockNumber"),
                            "transactionHash": result.get("transactionHash"),
                        }
                    )
            elif name == "newPendingTransactions" and isinstance(result, str):
                if result in seen_hashes:
                    continue
                seen_hashes.add(result)
                fetch_started = time.perf_counter()
                tx_response = rpc_call(
                    http_url,
                    "eth_getTransactionByHash",
                    [result],
                    timeout_s=3.0,
                )
                created = now_dt()
                fetch_latency_ms = (time.perf_counter() - fetch_started) * 1000
                event = build_pending_event(
                    result,
                    tx_response,
                    args.source,
                    args.chain_id,
                    created,
                    fetch_latency_ms,
                )
                output_path = pending_replay_path(root, created, event["event_id"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n")
                enqueue_latency_ms = (time.perf_counter() - received_at) * 1000
                enqueue_latencies.append(enqueue_latency_ms)
                pending_events.append(
                    {
                        "tx_hash": result,
                        "event_id": event["event_id"],
                        "raw_tx_status": event["raw_tx_status"],
                        "replay_path": str(output_path.relative_to(root)),
                        "enqueue_latency_ms": round(enqueue_latency_ms, 2),
                    }
                )
                if len(pending_events) >= args.max_pending:
                    break
    finally:
        sock.close()

    summary = {
        "checked_at": now_iso(),
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "source": args.source,
        "subscriptions_seen": sorted(set(subscription_names.values())),
        "pending_events_written": len(pending_events),
        "deduped_pending_hashes": len(seen_hashes),
        "head_samples": head_samples,
        "log_samples": log_samples,
        "pending_events": pending_events,
        "enqueue_latency_ms": {
            "p50": percentile(enqueue_latencies, 50),
            "p95": percentile(enqueue_latencies, 95),
            "max": round(max(enqueue_latencies), 2) if enqueue_latencies else None,
        },
        "provider_only_limitations": {
            "raw_tx_status": "unavailable_from_provider",
            "replacement_status": "unknown",
        },
        "errors": errors,
        "status": "ok" if pending_events and not errors else "degraded",
    }
    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
