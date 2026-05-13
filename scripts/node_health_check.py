#!/usr/bin/env python3
"""Ethereum RPC health checks for Phase 1.

The script uses the Python standard library and optionally certifi when it is
installed. Endpoint URLs are read from environment variables named in
config/rpc_endpoints.example.json.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
SSL_CONTEXT: ssl.SSLContext | None = None


@dataclass
class RpcResult:
    ok: bool
    latency_ms: float | None = None
    result: Any = None
    error: str | None = None
    method_missing: bool = False


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


def rpc_call(
    url: str,
    method: str,
    params: list[Any],
    timeout_s: float,
    rate_limiter: RateLimiter | None = None,
) -> RpcResult:
    if rate_limiter:
        rate_limiter.wait()
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_s, context=ssl_context()) as response:
            body = response.read()
    except HTTPError as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        body = exc.read()
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError:
            return RpcResult(
                ok=False,
                latency_ms=latency_ms,
                error=f"HTTP {exc.code}: {exc.reason}",
            )
        if "error" in decoded:
            return rpc_error_result(decoded["error"], latency_ms)
        return RpcResult(
            ok=False,
            latency_ms=latency_ms,
            error=f"HTTP {exc.code}: {decoded}",
        )
    except URLError as exc:
        return RpcResult(ok=False, error=str(exc))
    except TimeoutError:
        return RpcResult(ok=False, error="timeout")
    except OSError as exc:
        return RpcResult(ok=False, error=str(exc))

    latency_ms = (time.perf_counter() - started) * 1000
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return RpcResult(ok=False, latency_ms=latency_ms, error=str(exc))

    if "error" in decoded:
        return rpc_error_result(decoded["error"], latency_ms)
    return RpcResult(ok=True, latency_ms=latency_ms, result=decoded.get("result"))


def rpc_error_result(error: Any, latency_ms: float) -> RpcResult:
    if isinstance(error, dict):
        message = error.get("message", str(error))
        code = error.get("code")
    else:
        message = str(error)
        code = None
    return RpcResult(
        ok=False,
        latency_ms=latency_ms,
        error=f"{code}: {message}",
        method_missing=code == -32601,
    )


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


def read_ws_payload(sock: socket.socket) -> bytes:
    header = sock.recv(2)
    if len(header) < 2:
        raise OSError("short websocket header")
    first, second = header
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]
    if second & 0x80:
        mask = sock.recv(4)
        payload = sock.recv(length)
        return bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return sock.recv(length)


def ws_subscribe_new_heads(url: str, timeout_s: float) -> RpcResult:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return RpcResult(ok=False, error="missing websocket host")
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    started = time.perf_counter()
    try:
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
            return RpcResult(ok=False, error="websocket upgrade failed")
        subscribe = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_subscribe",
            "params": ["newHeads"],
        }
        sock.sendall(ws_frame(json.dumps(subscribe).encode("utf-8")))
        payload = read_ws_payload(sock)
        decoded = json.loads(payload)
        latency_ms = (time.perf_counter() - started) * 1000
        if "error" in decoded:
            return RpcResult(ok=False, latency_ms=latency_ms, error=str(decoded["error"]))
        return RpcResult(ok="result" in decoded, latency_ms=latency_ms, result=decoded)
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        return RpcResult(ok=False, error=str(exc))
    finally:
        try:
            sock.close()  # type: ignore[name-defined]
        except Exception:
            pass


def trace_check(
    url: str,
    client: str,
    timeout_s: float,
    rate_limiter: RateLimiter | None = None,
) -> RpcResult:
    tx = {"from": ZERO_ADDRESS, "to": ZERO_ADDRESS, "value": "0x0", "data": "0x"}
    if client == "erigon":
        result = rpc_call(
            url,
            "trace_call",
            [tx, ["trace", "stateDiff"], "pending"],
            timeout_s,
            rate_limiter,
        )
    else:
        result = rpc_call(
            url,
            "debug_traceCall",
            [tx, "pending", {}],
            timeout_s,
            rate_limiter,
        )
    if result.method_missing:
        return result
    # Permission, balance, or execution errors still prove the method exists.
    if (
        not result.ok
        and result.error
        and result.error.split(":", 1)[0] in {"-32602", "-32000", "-32001", "3"}
    ):
        return RpcResult(ok=True, latency_ms=result.latency_ms, result="method_available")
    return result


def required_checks_for(endpoint: dict[str, Any]) -> list[str]:
    if endpoint["role"] == "provider_fallback":
        return ["chain_id", "head", "websocket_new_heads"]
    return [
        "chain_id",
        "head",
        "peer_count",
        "txpool_api",
        "trace_api",
        "websocket_new_heads",
    ]


def check_endpoint(endpoint: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    http_url = os.getenv(endpoint["http_url_env"], "")
    ws_url = os.getenv(endpoint.get("ws_url_env", ""), "")
    timeout_s = config.get("trace_timeout_ms", 1500) / 1000
    rpc_max_rps = float(config.get("rpc_max_rps", 5.0))
    rpc_min_interval_ms = float(config.get("rpc_min_interval_ms", 200.0))
    rate_limiter = RateLimiter(rpc_max_rps, rpc_min_interval_ms)
    report: dict[str, Any] = {
        "name": endpoint["name"],
        "role": endpoint["role"],
        "client": endpoint["client"],
        "checked_at": now_iso(),
        "enabled": bool(http_url),
        "rpc_rate_limit": {
            "max_rps": rpc_max_rps,
            "min_interval_ms": rpc_min_interval_ms,
        },
        "checks": {},
    }
    if not http_url:
        report["status"] = "skipped"
        report["reason"] = f"unset env {endpoint['http_url_env']}"
        return report

    chain = rpc_call(http_url, "eth_chainId", [], timeout_s, rate_limiter)
    block = rpc_call(http_url, "eth_blockNumber", [], timeout_s, rate_limiter)
    if endpoint["role"] == "provider_fallback":
        peers = RpcResult(ok=False, error="skipped for provider_fallback")
        txpool = RpcResult(ok=False, error="skipped for provider_fallback")
        trace = RpcResult(ok=False, error="skipped for provider_fallback")
    else:
        peers = rpc_call(http_url, "net_peerCount", [], timeout_s, rate_limiter)
        txpool = rpc_call(http_url, "txpool_status", [], timeout_s, rate_limiter)
        trace = trace_check(http_url, endpoint["client"], timeout_s, rate_limiter)
    ws = ws_subscribe_new_heads(ws_url, timeout_s) if ws_url else RpcResult(False, error="unset ws url")

    report["checks"] = {
        "chain_id": result_dict(chain),
        "head": result_dict(block),
        "peer_count": result_dict(peers),
        "txpool_api": result_dict(txpool),
        "trace_api": result_dict(trace),
        "websocket_new_heads": result_dict(ws),
    }
    required_checks = required_checks_for(endpoint)
    report["required_checks"] = required_checks
    report["status"] = "ok" if all(
        report["checks"][name]["ok"]
        for name in required_checks
    ) else "degraded"
    return report


def result_dict(result: RpcResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "latency_ms": round(result.latency_ms, 2) if result.latency_ms else None,
        "result": result.result,
        "error": result.error,
        "method_missing": result.method_missing,
    }


def add_head_lag(reports: list[dict[str, Any]], threshold: int) -> None:
    heads = []
    for report in reports:
        raw = report.get("checks", {}).get("head", {}).get("result")
        if isinstance(raw, str) and raw.startswith("0x"):
            heads.append(int(raw, 16))
    if not heads:
        return
    max_head = max(heads)
    for report in reports:
        raw = report.get("checks", {}).get("head", {}).get("result")
        if isinstance(raw, str) and raw.startswith("0x"):
            lag = max_head - int(raw, 16)
            report["checks"]["head_lag"] = {
                "ok": lag <= threshold,
                "lag_blocks": lag,
                "max_observed_head": max_head,
            }


def recommend_active_endpoint(reports: list[dict[str, Any]]) -> str | None:
    priority = {"primary": 0, "backup": 1, "provider_fallback": 2}
    candidates = [
        report
        for report in reports
        if report.get("status") == "ok"
        and report.get("checks", {}).get("head_lag", {}).get("ok", True)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: priority.get(item.get("role"), 99))
    return candidates[0]["name"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/rpc_endpoints.example.json",
        help="RPC endpoint config JSON",
    )
    parser.add_argument("--out", help="optional report output JSON path")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    reports = [check_endpoint(endpoint, config) for endpoint in config["endpoints"]]
    add_head_lag(reports, int(config.get("head_lag_threshold_blocks", 2)))
    output = {
        "checked_at": now_iso(),
        "chain_id": config["chain_id"],
        "active_endpoint_recommendation": recommend_active_endpoint(reports),
        "endpoints": reports,
    }
    serialized = json.dumps(output, indent=2, sort_keys=True)
    print(serialized)
    if args.out:
        Path(args.out).write_text(serialized + "\n", encoding="utf-8")
    return 0 if output["active_endpoint_recommendation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
