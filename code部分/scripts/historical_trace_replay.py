#!/usr/bin/env python3
"""Replay historical exploit candidates through a Geth or Erigon trace endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import time
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SSL_CONTEXT: ssl.SSLContext | None = None
TRACE_METHODS = ["debug_traceTransaction", "trace_transaction"]


def retry_count(value: str) -> int:
    number = int(value)
    if number < 0 or number > 1:
        raise argparse.ArgumentTypeError("retries must be 0 or 1 for cost-controlled replay")
    return number


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


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


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def event_id_for(chain_id: int, tx_hash: str, source: str) -> str:
    seed = f"trace-bundle.v1:{chain_id}:{tx_hash}:{source}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def replay_path(root: Path, created_at: datetime, event_id: str) -> Path:
    return (
        root
        / "data"
        / "replay"
        / "trace-bundle.v1"
        / f"dt={created_at.strftime('%Y-%m-%d')}"
        / f"hour={created_at.strftime('%H')}"
        / f"{event_id}.json"
    )


def raw_trace_path(root: Path, created_at: datetime, tx_hash: str, source: str) -> Path:
    return (
        root
        / "data"
        / "raw-trace"
        / "chain_id=1"
        / f"dt={created_at.strftime('%Y-%m-%d')}"
        / f"hour={created_at.strftime('%H')}"
        / f"1-{tx_hash}-{source}.json"
    )


def rpc_call(url: str, method: str, params: list[Any], timeout_s: float) -> tuple[dict[str, Any], float]:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_s, context=ssl_context()) as response:
            body = json.loads(response.read())
    except HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except json.JSONDecodeError:
            body = {"error": {"code": f"http_{exc.code}", "message": exc.reason}}
    except (URLError, TimeoutError, OSError, HTTPException, json.JSONDecodeError) as exc:
        body = {"error": {"code": "transport_error", "message": str(exc)}}
    return body, (time.perf_counter() - started) * 1000


def flatten_geth_call(node: dict[str, Any], depth: int = 0) -> list[dict[str, Any]]:
    item = {
        "type": node.get("type"),
        "from": node.get("from"),
        "to": node.get("to"),
        "input": node.get("input"),
        "output": node.get("output"),
        "value": node.get("value"),
        "gas": node.get("gas"),
        "gasUsed": node.get("gasUsed"),
        "error": node.get("error"),
        "depth": depth,
    }
    calls = [item]
    for child in node.get("calls") or []:
        if isinstance(child, dict):
            calls.extend(flatten_geth_call(child, depth + 1))
    return calls


def normalize_trace(source: str, result: Any) -> tuple[list[Any], list[Any], dict[str, Any]]:
    if source == "debug_traceTransaction":
        if isinstance(result, dict):
            logs = result.get("logs") if isinstance(result.get("logs"), list) else []
            return flatten_geth_call(result), logs, {}
        return [], [], {}
    if source == "trace_transaction":
        if isinstance(result, list):
            return result, [], {}
        if isinstance(result, dict):
            calls = result.get("trace") if isinstance(result.get("trace"), list) else []
            state_diff = result.get("stateDiff") if isinstance(result.get("stateDiff"), dict) else {}
            return calls, [], state_diff
    return [], [], {}


def build_bundle(
    item: dict[str, Any],
    source: str,
    status: str,
    calls: list[Any],
    logs: list[Any],
    state_diff: dict[str, Any],
    trace_error: dict[str, Any] | None,
    raw_trace_ref: str | None,
) -> dict[str, Any]:
    created = now_dt()
    chain_id = item["chain_id"]
    tx_hash = item["tx_hash"]
    return {
        "event_id": event_id_for(chain_id, tx_hash, source),
        "schema_ver": "trace-bundle.v1",
        "chain_id": chain_id,
        "created_at": created.isoformat(timespec="milliseconds"),
        "observed_at": item.get("observed_at") or item.get("seen_at") or item.get("created_at"),
        "idempotency_key": f"{chain_id}:{tx_hash}:{source}",
        "tx_hash": tx_hash,
        "trace_source": source,
        "trace_status": status,
        "trace_error": trace_error,
        "calls": calls,
        "logs": logs,
        "token_transfers": [],
        "state_diff": state_diff,
        "raw_trace_ref": raw_trace_ref,
    }


def error_object(source: str, response: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    error = response.get("error")
    if isinstance(error, dict):
        return {
            "source": source,
            "code": error.get("code"),
            "message": error.get("message"),
            "latency_ms": round(latency_ms, 2),
        }
    return {
        "source": source,
        "code": "unknown_error",
        "message": str(error),
        "latency_ms": round(latency_ms, 2),
    }


def result_is_nonempty(method: str, result: Any) -> bool:
    if method == "trace_transaction":
        return isinstance(result, list) and bool(result)
    if method == "debug_traceTransaction":
        return isinstance(result, dict) and bool(result)
    return result is not None


def rpc_error(method: str, response: dict[str, Any], latency_ms: float, fallback: str) -> dict[str, Any]:
    if isinstance(response.get("error"), dict):
        return error_object(method, response, latency_ms)
    return {
        "source": method,
        "code": fallback,
        "message": fallback.replace("_", " "),
        "latency_ms": round(latency_ms, 2),
    }


def validated_rpc_call(
    url: str,
    method: str,
    params: list[Any],
    timeout_s: float,
    retries: int,
    validator: Any,
    fallback_error: str,
) -> tuple[Any | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for attempt_index in range(retries + 1):
        response, latency_ms = rpc_call(url, method, params, timeout_s)
        result = response.get("result")
        ok = bool(validator(result))
        attempt: dict[str, Any] = {
            "method": method,
            "attempt": attempt_index + 1,
            "latency_ms": round(latency_ms, 2),
            "ok": ok,
        }
        if not ok:
            attempt["error"] = rpc_error(method, response, latency_ms, fallback_error)
        attempts.append(attempt)
        if ok:
            return result, attempts
    return None, attempts


def fetch_transaction_context(
    url: str,
    tx_hash: str,
    timeout_s: float,
    retries: int,
    block_context_cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[Any], list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    tx_result, tx_calls = validated_rpc_call(
        url,
        "eth_getTransactionByHash",
        [tx_hash],
        timeout_s,
        retries,
        lambda result: isinstance(result, dict)
        and str(result.get("hash", "")).lower() == tx_hash.lower()
        and isinstance(result.get("blockHash"), str),
        "transaction_not_found_or_mismatched",
    )
    calls.extend(tx_calls)
    if tx_result is None:
        return None, [], calls

    receipt, receipt_calls = validated_rpc_call(
        url,
        "eth_getTransactionReceipt",
        [tx_hash],
        timeout_s,
        retries,
        lambda result: isinstance(result, dict)
        and str(result.get("transactionHash", "")).lower() == tx_hash.lower()
        and isinstance(result.get("blockHash"), str)
        and result.get("blockHash") == tx_result.get("blockHash"),
        "receipt_not_found_or_mismatched",
    )
    calls.extend(receipt_calls)
    if receipt is None:
        return None, [], calls

    block_hash = receipt["blockHash"]
    cached_block = (block_context_cache or {}).get(str(block_hash).lower())
    if (
        isinstance(cached_block, dict)
        and cached_block.get("block_number") == receipt.get("blockNumber")
        and isinstance(cached_block.get("observed_at"), str)
    ):
        calls.append(
            {
                "method": "local_block_context_cache",
                "attempt": 1,
                "latency_ms": 0.0,
                "ok": True,
            }
        )
        logs = receipt.get("logs") if isinstance(receipt.get("logs"), list) else []
        return {
            "tx_hash": tx_hash.lower(),
            "block_hash": block_hash,
            "block_number": receipt.get("blockNumber"),
            "receipt_status": receipt.get("status"),
            "log_count": len(logs),
            "observed_at": cached_block["observed_at"],
        }, logs, calls

    block, block_calls = validated_rpc_call(
        url,
        "eth_getBlockByHash",
        [block_hash, False],
        timeout_s,
        retries,
        lambda result: isinstance(result, dict)
        and result.get("hash") == block_hash
        and isinstance(result.get("timestamp"), str),
        "block_not_found_or_mismatched",
    )
    calls.extend(block_calls)
    if block is None:
        return None, [], calls

    try:
        observed_at = datetime.fromtimestamp(int(block["timestamp"], 16), timezone.utc).isoformat(
            timespec="milliseconds"
        )
    except (TypeError, ValueError, OSError):
        calls[-1]["ok"] = False
        calls[-1]["error"] = {
            "source": "eth_getBlockByHash",
            "code": "invalid_block_timestamp",
            "message": "invalid block timestamp",
            "latency_ms": calls[-1]["latency_ms"],
        }
        return None, [], calls

    logs = receipt.get("logs") if isinstance(receipt.get("logs"), list) else []
    context = {
        "tx_hash": tx_hash.lower(),
        "block_hash": block_hash,
        "block_number": receipt.get("blockNumber"),
        "receipt_status": receipt.get("status"),
        "log_count": len(logs),
        "observed_at": observed_at,
    }
    return context, logs, calls


def load_block_context_cache(root: Path) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    reports_root = root / "ops" / "reports"
    for path in sorted(reports_root.glob("*historical-trace-replay*.json")):
        try:
            report = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        for item in report.get("transaction_contexts", []):
            context = item.get("context") if isinstance(item, dict) else None
            if not isinstance(context, dict):
                continue
            block_hash = context.get("block_hash")
            if isinstance(block_hash, str) and isinstance(context.get("observed_at"), str):
                cache[block_hash.lower()] = {
                    "block_number": context.get("block_number"),
                    "observed_at": context["observed_at"],
                }
    return cache


def existing_success(root: Path, tx_hash: str, method: str) -> tuple[dict[str, Any], Path] | None:
    trace_root = root / "data" / "replay" / "trace-bundle.v1"
    allowed = set(TRACE_METHODS) if method == "auto" else {method}
    for path in sorted(trace_root.glob("dt=*/hour=*/*.json"), reverse=True):
        try:
            bundle = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        raw_ref = bundle.get("raw_trace_ref")
        if (
            str(bundle.get("tx_hash", "")).lower() == tx_hash.lower()
            and bundle.get("trace_source") in allowed
            and bundle.get("trace_status") == "ok"
            and isinstance(bundle.get("calls"), list)
            and bool(bundle["calls"])
            and isinstance(raw_ref, str)
            and (root / raw_ref).exists()
        ):
            return bundle, path
    return None


def validate_queue_item(item: dict[str, Any]) -> list[str]:
    errors = []
    if item.get("chain_id") != 1 or item.get("chain") != "ethereum":
        errors.append("only ethereum chain_id=1 items are supported")
    tx_hash = item.get("tx_hash")
    if not isinstance(tx_hash, str) or not tx_hash.startswith("0x") or len(tx_hash) != 66:
        errors.append("invalid tx_hash")
    if not item.get("incident_id"):
        errors.append("missing incident_id")
    return errors


def trace_item(
    root: Path,
    item: dict[str, Any],
    url: str,
    method: str,
    timeout_s: float,
    retries: int,
    receipt_logs: list[Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = []
    for attempt_index in range(retries + 1):
        response, latency_ms = rpc_call(url, method, [item["tx_hash"]], timeout_s)
        ok = (
            "result" in response
            and "error" not in response
            and result_is_nonempty(method, response.get("result"))
        )
        attempt = {
            "source": method,
            "attempt": attempt_index + 1,
            "latency_ms": round(latency_ms, 2),
            "ok": ok,
        }
        attempts.append(attempt)
        if ok:
            created = now_dt()
            raw_path = raw_trace_path(root, created, item["tx_hash"], method)
            write_json(raw_path, response["result"])
            calls, logs, state_diff = normalize_trace(method, response["result"])
            if receipt_logs is not None:
                logs = receipt_logs
            bundle = build_bundle(
                item,
                method,
                "ok",
                calls,
                logs,
                state_diff,
                None,
                str(raw_path.relative_to(root)),
            )
            return bundle, {"attempts": attempts, "selected": method}
        attempt["error"] = rpc_error(method, response, latency_ms, "empty_trace_result")

    bundle = build_bundle(
        item,
        method,
        "failed",
        [],
        [],
        {},
        {
            "code": "historical_trace_failed",
            "message": "All historical trace attempts failed.",
            "queue_id": item.get("queue_id"),
            "incident_id": item.get("incident_id"),
            "attempts": attempts,
        },
        None,
    )
    return bundle, {"attempts": attempts, "selected": method}


def trace_item_auto(
    root: Path,
    item: dict[str, Any],
    url: str,
    method: str,
    timeout_s: float,
    retries: int,
    receipt_logs: list[Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    methods = TRACE_METHODS if method == "auto" else [method]
    all_attempts = []
    last_bundle = None
    for candidate_method in methods:
        bundle, meta = trace_item(
            root, item, url, candidate_method, timeout_s, retries, receipt_logs=receipt_logs
        )
        all_attempts.extend(meta["attempts"])
        last_bundle = bundle
        if bundle["trace_status"] == "ok":
            return bundle, {"attempts": all_attempts, "selected": candidate_method}
    assert last_bundle is not None
    return last_bundle, {"attempts": all_attempts, "selected": "none"}


def main_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay historical transaction traces.")
    parser.add_argument("--queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--out", default="ops/reports/historical-trace-replay.latest.json")
    parser.add_argument("--rpc-url", default=os.environ.get("ETH_MAIN_HTTP_URL"))
    parser.add_argument(
        "--method",
        choices=["auto", "debug_traceTransaction", "trace_transaction"],
        default=os.environ.get("HISTORICAL_TRACE_METHOD", "trace_transaction"),
    )
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--retries", type=retry_count, default=1)
    parser.add_argument("--inter-item-delay-s", type=float, default=0.0)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="0 means all queue items")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--fail-fast",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stop after the first failed trace. Enabled by default for cost control.",
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse an existing successful trace_transaction bundle instead of paying twice.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate queue without RPC calls")
    parser.add_argument(
        "--write-failed-bundles",
        action="store_true",
        help="Persist failed TraceBundle records. By default only ok traces are written.",
    )
    args = parser.parse_args(argv)

    root = Path.cwd()
    queue = read_json(root / args.queue)
    items = queue.get("items", [])
    if args.start_index < 0:
        parser.error("--start-index must be non-negative")
    if args.inter_item_delay_s < 0:
        parser.error("--inter-item-delay-s must be non-negative")
    items = items[args.start_index :]
    if args.limit > 0:
        items = items[: args.limit]

    validation_errors = []
    for item in items:
        errors = validate_queue_item(item)
        if errors:
            validation_errors.append({"queue_id": item.get("queue_id"), "errors": errors})

    written = []
    attempts = []
    transaction_contexts = []
    chain_check: dict[str, Any] = {"performed": False, "ok": False, "chain_id": None}
    reused_existing = 0
    block_context_cache = load_block_context_cache(root)
    status = "ok"
    if validation_errors:
        status = "failed"
    elif args.dry_run:
        status = "dry_run_ok"
    elif not args.rpc_url:
        status = "missing_endpoint"
    else:
        chain_response, chain_latency = rpc_call(args.rpc_url, "eth_chainId", [], args.timeout_s)
        chain_id = chain_response.get("result")
        chain_check = {
            "performed": True,
            "ok": chain_id == "0x1",
            "chain_id": chain_id,
            "latency_ms": round(chain_latency, 2),
        }
        if not chain_check["ok"]:
            chain_check["error"] = rpc_error(
                "eth_chainId", chain_response, chain_latency, "ethereum_mainnet_required"
            )
            status = "wrong_chain"
        for item in items if chain_check["ok"] else []:
            existing = existing_success(root, item["tx_hash"], args.method) if args.skip_existing else None
            if existing is not None:
                bundle, output_path = existing
                reused_existing += 1
                written.append(
                    {
                        "event_id": bundle["event_id"],
                        "incident_id": item.get("incident_id"),
                        "tx_hash": item["tx_hash"],
                        "trace_source": bundle["trace_source"],
                        "trace_status": "ok",
                        "replay_path": str(output_path.relative_to(root)),
                        "persisted": True,
                        "reused_existing": True,
                    }
                )
                attempts.append(
                    {"queue_id": item.get("queue_id"), "attempts": [], "selected": "existing_bundle"}
                )
                continue

            if args.inter_item_delay_s > 0:
                time.sleep(args.inter_item_delay_s)
            context, receipt_logs, context_calls = fetch_transaction_context(
                args.rpc_url,
                item["tx_hash"],
                args.timeout_s,
                args.retries,
                block_context_cache=block_context_cache,
            )
            if context is not None:
                block_context_cache[str(context["block_hash"]).lower()] = {
                    "block_number": context.get("block_number"),
                    "observed_at": context["observed_at"],
                }
            transaction_contexts.append(
                {
                    "queue_id": item.get("queue_id"),
                    "tx_hash": item["tx_hash"],
                    "context": context,
                    "calls": context_calls,
                }
            )
            if context is None:
                source = args.method if args.method != "auto" else "trace_transaction"
                bundle = build_bundle(
                    item,
                    source,
                    "failed",
                    [],
                    [],
                    {},
                    {
                        "code": "transaction_context_validation_failed",
                        "message": "Transaction, receipt, or block context validation failed.",
                        "queue_id": item.get("queue_id"),
                        "attempts": context_calls,
                    },
                    None,
                )
                trace_meta = {"attempts": [], "selected": "none"}
            else:
                enriched_item = {**item, "observed_at": context["observed_at"]}
                bundle, trace_meta = trace_item_auto(
                    root,
                    enriched_item,
                    args.rpc_url,
                    args.method,
                    args.timeout_s,
                    args.retries,
                    receipt_logs=receipt_logs,
                )
            written_item = {
                "event_id": bundle["event_id"],
                "incident_id": item.get("incident_id"),
                "tx_hash": item["tx_hash"],
                "trace_source": bundle["trace_source"],
                "trace_status": bundle["trace_status"],
                "replay_path": None,
                "persisted": False,
            }
            if bundle["trace_status"] == "ok" or args.write_failed_bundles:
                output_path = replay_path(root, now_dt(), bundle["event_id"])
                write_json(output_path, bundle)
                written_item["replay_path"] = str(output_path.relative_to(root))
                written_item["persisted"] = True
            written.append(written_item)
            attempts.append({"queue_id": item.get("queue_id"), **trace_meta})
            if args.fail_fast and bundle["trace_status"] != "ok":
                break
        if not written or any(item["trace_status"] != "ok" for item in written):
            status = "degraded"

    report = {
        "checked_at": now_dt().isoformat(timespec="milliseconds"),
        "status": status,
        "queue": args.queue,
        "run_id": args.run_id,
        "queue_items_seen": len(items),
        "method": args.method,
        "dry_run": args.dry_run,
        "endpoint_configured": bool(args.rpc_url),
        "write_failed_bundles": args.write_failed_bundles,
        "fail_fast": args.fail_fast,
        "max_retries": args.retries,
        "inter_item_delay_s": args.inter_item_delay_s,
        "start_index": args.start_index,
        "skip_existing": args.skip_existing,
        "reused_existing_bundles": reused_existing,
        "chain_check": chain_check,
        "transaction_contexts": transaction_contexts,
        "block_context_cache_entries": len(block_context_cache),
        "block_context_cache_hits": sum(
            1
            for item in transaction_contexts
            for call in item.get("calls", [])
            if call.get("method") == "local_block_context_cache" and call.get("ok") is True
        ),
        "rpc_call_summary": {
            "chain_checks": 1 if chain_check["performed"] else 0,
            "transaction_context_calls": sum(len(item["calls"]) for item in transaction_contexts),
            "trace_attempts": sum(len(item.get("attempts", [])) for item in attempts),
        },
        "provider_cost_note": "Inspect the provider billing dashboard; JSON-RPC responses do not include invoice cost.",
        "written_trace_bundles": sum(1 for item in written if item["persisted"]),
        "ok_trace_bundles": sum(1 for item in written if item["trace_status"] == "ok"),
        "failed_trace_bundles": sum(1 for item in written if item["trace_status"] != "ok"),
        "written": written,
        "attempts": attempts,
        "validation_errors": validation_errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status in {"ok", "dry_run_ok"} else 2


def main() -> int:
    return main_args()


if __name__ == "__main__":
    raise SystemExit(main())
