#!/usr/bin/env python3
"""Provider-only WebSocket smoke test for Phase 1.

This script validates that the configured provider can establish the three
subscriptions needed for provider-only development:

- newHeads
- newPendingTransactions
- logs for the Phase 0 protocol whitelist
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import ssl
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SSL_CONTEXT: ssl.SSLContext | None = None


class RateLimiter:
    def __init__(self, min_interval_ms: float) -> None:
        self.interval_s = min_interval_ms / 1000 if min_interval_ms > 0 else 0.0
        self.next_allowed = 0.0

    def wait(self) -> None:
        if self.interval_s <= 0:
            return
        now = time.monotonic()
        if now < self.next_allowed:
            time.sleep(self.next_allowed - now)
            now = time.monotonic()
        self.next_allowed = now + self.interval_s


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


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


def load_addresses(path: Path) -> list[str]:
    config = json.loads(path.read_text(encoding="utf-8"))
    return [item["address"] for item in config["addresses"]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws-url-env", default="ETH_PROVIDER_WS_URL")
    parser.add_argument(
        "--addresses",
        default="config/protocol_log_addresses.json",
        help="JSON file containing protocol log addresses",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--pending-samples", type=int, default=5)
    parser.add_argument(
        "--subscription-min-interval-ms",
        type=float,
        default=200.0,
        help="minimum delay between WebSocket subscription requests",
    )
    parser.add_argument("--out", default="ops/reports/provider-smoke.latest.json")
    args = parser.parse_args()

    ws_url = os.getenv(args.ws_url_env)
    if not ws_url:
        raise SystemExit(f"missing env {args.ws_url_env}")

    root = Path(__file__).resolve().parents[1]
    addresses = load_addresses(root / args.addresses)
    report: dict[str, Any] = {
        "checked_at": now_iso(),
        "provider_ws_env": args.ws_url_env,
        "subscription_rate_limit": {
            "min_interval_ms": args.subscription_min_interval_ms,
        },
        "subscriptions": {},
        "samples": {
            "newHeads": [],
            "newPendingTransactions": [],
            "logs": [],
        },
    }

    request_names = {
        1: "newHeads",
        2: "newPendingTransactions",
        3: "logs",
    }
    subscription_names: dict[str, str] = {}

    started = time.monotonic()
    subscription_limiter = RateLimiter(args.subscription_min_interval_ms)
    sock = connect_ws(ws_url, args.timeout)
    try:
        subscription_limiter.wait()
        send_rpc(sock, 1, "eth_subscribe", ["newHeads"])
        subscription_limiter.wait()
        send_rpc(sock, 2, "eth_subscribe", ["newPendingTransactions"])
        subscription_limiter.wait()
        send_rpc(sock, 3, "eth_subscribe", ["logs", {"address": addresses}])

        while time.monotonic() - started < args.timeout:
            try:
                message = json.loads(read_ws_payload(sock))
            except socket.timeout:
                continue
            if "id" in message:
                name = request_names.get(message["id"], f"request_{message['id']}")
                if "result" in message:
                    subscription_id = message["result"]
                    report["subscriptions"][name] = {
                        "ok": True,
                        "subscription_id": subscription_id,
                    }
                    subscription_names[subscription_id] = name
                else:
                    report["subscriptions"][name] = {
                        "ok": False,
                        "error": message.get("error"),
                    }
                continue

            params = message.get("params", {})
            subscription_id = params.get("subscription")
            name = subscription_names.get(subscription_id)
            if not name:
                continue
            samples = report["samples"][name]
            if name == "newPendingTransactions":
                if len(samples) < args.pending_samples:
                    samples.append(params.get("result"))
            elif name == "newHeads":
                if len(samples) < 1:
                    result = params.get("result", {})
                    samples.append(
                        {
                            "number": result.get("number"),
                            "hash": result.get("hash"),
                        }
                    )
            elif name == "logs":
                if len(samples) < 3:
                    result = params.get("result", {})
                    samples.append(
                        {
                            "address": result.get("address"),
                            "blockNumber": result.get("blockNumber"),
                            "transactionHash": result.get("transactionHash"),
                        }
                    )

            if (
                len(report["samples"]["newPendingTransactions"]) >= args.pending_samples
                and report["samples"]["newHeads"]
                and all(item.get("ok") for item in report["subscriptions"].values())
            ):
                break
    finally:
        sock.close()

    report["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    for name in request_names.values():
        report["subscriptions"].setdefault(
            name,
            {"ok": False, "error": "no subscription response before timeout"},
        )
    report["status"] = "ok" if all(
        report["subscriptions"][name]["ok"] for name in request_names.values()
    ) else "degraded"

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
