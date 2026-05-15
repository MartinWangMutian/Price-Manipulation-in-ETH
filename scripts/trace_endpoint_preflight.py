#!/usr/bin/env python3
"""Preflight a historical trace endpoint without writing replay bundles."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from historical_trace_replay import read_json, rpc_call, validate_queue_item, write_json

TRACE_METHODS = ["debug_traceTransaction", "trace_transaction"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def ok_response(response: dict[str, Any]) -> bool:
    return "result" in response and "error" not in response


def summarize_error(response: dict[str, Any]) -> Any:
    if "error" in response:
        return response["error"]
    return None


def trace_check(
    url: str,
    method: str,
    tx_hash: str,
    timeout_s: float,
) -> dict[str, Any]:
    response, latency_ms = rpc_call(url, method, [tx_hash], timeout_s)
    trace_ok = ok_response(response)
    result = response.get("result")
    return {
        "name": method,
        "ok": trace_ok,
        "latency_ms": round(latency_ms, 2),
        "tx_hash": tx_hash,
        "result_shape": {
            "type": type(result).__name__ if trace_ok else None,
            "empty": result in ({}, [], None),
        },
        "error": summarize_error(response),
    }


def main_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight trace endpoint capabilities.")
    parser.add_argument("--queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--out", default="ops/reports/trace-endpoint-preflight.latest.json")
    parser.add_argument("--rpc-url", default=os.environ.get("ETH_MAIN_HTTP_URL"))
    parser.add_argument(
        "--method",
        choices=["auto", "debug_traceTransaction", "trace_transaction"],
        default=os.environ.get("HISTORICAL_TRACE_METHOD", "auto"),
    )
    parser.add_argument("--timeout-s", type=float, default=15.0)
    args = parser.parse_args(argv)

    root = Path.cwd()
    queue = read_json(root / args.queue)
    items = queue.get("items", [])
    validation_errors = []
    item = items[0] if items else None
    if item is None:
        validation_errors.append({"queue": args.queue, "errors": ["queue has no items"]})
    else:
        errors = validate_queue_item(item)
        if errors:
            validation_errors.append({"queue_id": item.get("queue_id"), "errors": errors})

    checks: list[dict[str, Any]] = []
    selected_method = None
    status = "ok"
    if validation_errors:
        status = "failed"
    elif not args.rpc_url:
        status = "missing_endpoint"
    else:
        chain_response, chain_latency_ms = rpc_call(args.rpc_url, "eth_chainId", [], args.timeout_s)
        chain_ok = ok_response(chain_response) and chain_response.get("result") == "0x1"
        checks.append(
            {
                "name": "eth_chainId",
                "ok": chain_ok,
                "latency_ms": round(chain_latency_ms, 2),
                "result": chain_response.get("result"),
                "error": summarize_error(chain_response),
            }
        )
        methods = TRACE_METHODS if args.method == "auto" else [args.method]
        for method in methods:
            check = trace_check(args.rpc_url, method, item["tx_hash"], args.timeout_s)
            checks.append(check)
            if check["ok"]:
                selected_method = method
                break
        if not all(check["ok"] for check in checks):
            status = "ok" if checks[0]["ok"] and selected_method else "degraded"

    report = {
        "checked_at": now_iso(),
        "status": status,
        "queue": args.queue,
        "method": args.method,
        "selected_method": selected_method,
        "endpoint_configured": bool(args.rpc_url),
        "validation_errors": validation_errors,
        "checks": checks,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status == "ok" else 2


def main() -> int:
    return main_args()


if __name__ == "__main__":
    raise SystemExit(main())
