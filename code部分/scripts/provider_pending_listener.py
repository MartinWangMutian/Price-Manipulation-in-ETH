#!/usr/bin/env python3
"""Provider-only pending transaction listener.

The listener subscribes to `newPendingTransactions`, fetches transaction objects
with `eth_getTransactionByHash`, emits `PendingTxEvent` records, and writes them
to replay storage.
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
TX_HASH_LEN = 66


class RateLimiter:
    def __init__(self, max_rps: float, min_interval_ms: float) -> None:
        rps_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        ms_interval = min_interval_ms / 1000 if min_interval_ms > 0 else 0.0
        self.interval_s = max(rps_interval, ms_interval)
        self.next_allowed = 0.0

    def wait(self) -> None:
        if self.interval_s <= 0:
            return
        now = time.monotonic()
        if now < self.next_allowed:
            time.sleep(self.next_allowed - now)
            now = time.monotonic()
        self.next_allowed = now + self.interval_s


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
            body = json.loads(exc.read())
        except json.JSONDecodeError:
            body = {"error": f"HTTP {exc.code}: {exc.reason}"}
        return body
    except (URLError, TimeoutError, OSError) as exc:
        return {"error": str(exc)}


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
    if parsed.scheme == "wss":
        sock = ssl_context().wrap_socket(raw_sock, server_hostname=host)
    else:
        sock = raw_sock
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
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }
    sock.sendall(ws_frame(json.dumps(payload).encode("utf-8")))


def event_id_for(chain_id: int, tx_hash: str, source: str) -> str:
    seed = f"pending-tx.v1:{chain_id}:{tx_hash}:{source}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def replay_path(root: Path, created_at: datetime, event_id: str) -> Path:
    date_part = created_at.strftime("%Y-%m-%d")
    hour_part = created_at.strftime("%H")
    return (
        root
        / "data"
        / "replay"
        / "pending-tx.v1"
        / f"dt={date_part}"
        / f"hour={hour_part}"
        / f"{event_id}.json"
    )


def build_event(
    tx_hash: str,
    tx_response: dict[str, Any],
    source: str,
    chain_id: int,
) -> dict[str, Any]:
    created = now_dt()
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
    }


def validate_event(event: dict[str, Any]) -> list[str]:
    errors = []
    required = {
        "event_id",
        "schema_ver",
        "chain_id",
        "created_at",
        "idempotency_key",
        "tx_hash",
        "seen_at",
        "source",
        "raw_tx_status",
    }
    missing = sorted(required - set(event))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if event.get("schema_ver") != "pending-tx.v1":
        errors.append("schema_ver must be pending-tx.v1")
    tx_hash = event.get("tx_hash", "")
    if not (
        isinstance(tx_hash, str)
        and len(tx_hash) == TX_HASH_LEN
        and tx_hash.startswith("0x")
    ):
        errors.append("tx_hash is not a 32-byte hex string")
    if event.get("chain_id") != 1:
        errors.append("chain_id must be 1")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws-url-env", default="ETH_PROVIDER_WS_URL")
    parser.add_argument("--http-url-env", default="ETH_PROVIDER_HTTP_URL")
    parser.add_argument("--source", default="provider-pending-fallback")
    parser.add_argument("--chain-id", type=int, default=1)
    parser.add_argument("--max-events", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--http-max-rps",
        type=float,
        default=5.0,
        help="maximum eth_getTransactionByHash HTTP RPC requests per second",
    )
    parser.add_argument(
        "--http-min-interval-ms",
        type=float,
        default=200.0,
        help="minimum delay between HTTP RPC requests",
    )
    parser.add_argument(
        "--summary-out",
        default="ops/reports/pending-listener.latest.json",
    )
    args = parser.parse_args()

    ws_url = os.getenv(args.ws_url_env)
    http_url = os.getenv(args.http_url_env)
    if not ws_url:
        raise SystemExit(f"missing env {args.ws_url_env}")
    if not http_url:
        raise SystemExit(f"missing env {args.http_url_env}")

    root = Path(__file__).resolve().parents[1]
    started = time.monotonic()
    seen_hashes: set[str] = set()
    events: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    http_limiter = RateLimiter(args.http_max_rps, args.http_min_interval_ms)

    sock = connect_ws(ws_url, args.timeout)
    try:
        send_rpc(sock, 1, "eth_subscribe", ["newPendingTransactions"])
        subscription_id = None
        while time.monotonic() - started < args.timeout:
            try:
                message = json.loads(read_ws_payload(sock))
            except socket.timeout:
                continue
            if message.get("id") == 1:
                if "result" not in message:
                    raise SystemExit(f"subscription failed: {message.get('error')}")
                subscription_id = message["result"]
                continue

            params = message.get("params", {})
            if subscription_id and params.get("subscription") != subscription_id:
                continue
            tx_hash = params.get("result")
            if not isinstance(tx_hash, str) or tx_hash in seen_hashes:
                continue
            seen_hashes.add(tx_hash)
            http_limiter.wait()
            fetched_at = time.perf_counter()
            tx_response = rpc_call(
                http_url,
                "eth_getTransactionByHash",
                [tx_hash],
                timeout_s=3.0,
            )
            event = build_event(tx_hash, tx_response, args.source, args.chain_id)
            event["fetch_latency_ms"] = round((time.perf_counter() - fetched_at) * 1000, 2)
            validation_errors = validate_event(event)
            if validation_errors:
                errors.append({"tx_hash": tx_hash, "errors": validation_errors})
                continue
            path = replay_path(root, now_dt(), event["event_id"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n")
            events.append(
                {
                    "event_id": event["event_id"],
                    "tx_hash": tx_hash,
                    "raw_tx_status": event["raw_tx_status"],
                    "replay_path": str(path.relative_to(root)),
                    "fetch_latency_ms": event["fetch_latency_ms"],
                }
            )
            if len(events) >= args.max_events:
                break
    finally:
        sock.close()

    summary = {
        "checked_at": now_iso(),
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "source": args.source,
        "requested_events": args.max_events,
        "written_events": len(events),
        "deduped_hashes": len(seen_hashes),
        "http_rate_limit": {
            "max_rps": args.http_max_rps,
            "min_interval_ms": args.http_min_interval_ms,
        },
        "events": events,
        "errors": errors,
        "status": "ok" if events else "degraded",
    }
    out_path = root / args.summary_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if events else 2


if __name__ == "__main__":
    raise SystemExit(main())
