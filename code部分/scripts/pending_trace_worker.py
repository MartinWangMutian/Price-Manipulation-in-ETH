#!/usr/bin/env python3
"""Pending trace worker for Phase 2-B.

Reads PendingTxEvent replay records, tries pending simulation through Geth
`debug_traceCall` and Erigon `trace_call`, and falls back to an auditable
lightweight TraceBundle when no trace endpoint is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import ssl


SSL_CONTEXT: ssl.SSLContext | None = None


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


def event_id_for(chain_id: int, tx_hash: str, source: str) -> str:
    seed = f"trace-bundle.v1:{chain_id}:{tx_hash}:{source}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def replay_path(root: Path, created_at: datetime, event_id: str) -> Path:
    date_part = created_at.strftime("%Y-%m-%d")
    hour_part = created_at.strftime("%H")
    return (
        root
        / "data"
        / "replay"
        / "trace-bundle.v1"
        / f"dt={date_part}"
        / f"hour={hour_part}"
        / f"{event_id}.json"
    )


def raw_trace_path(root: Path, created_at: datetime, tx_hash: str, source: str) -> Path:
    date_part = created_at.strftime("%Y-%m-%d")
    hour_part = created_at.strftime("%H")
    return (
        root
        / "data"
        / "raw-trace"
        / "chain_id=1"
        / f"dt={date_part}"
        / f"hour={hour_part}"
        / f"1-{tx_hash}-{source}.json"
    )


def rpc_call(
    url: str,
    method: str,
    params: list[Any],
    timeout_s: float,
) -> tuple[dict[str, Any], float]:
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
            body = json.loads(response.read())
    except HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except json.JSONDecodeError:
            body = {"error": {"code": f"http_{exc.code}", "message": exc.reason}}
    except (URLError, TimeoutError, OSError) as exc:
        body = {"error": {"code": "transport_error", "message": str(exc)}}
    latency_ms = (time.perf_counter() - started) * 1000
    return body, latency_ms


def pending_call_object(pending_event: dict[str, Any]) -> dict[str, Any] | None:
    tx = pending_event.get("tx")
    if not isinstance(tx, dict):
        return None
    call: dict[str, Any] = {}
    field_map = {
        "from": "from",
        "to": "to",
        "gas": "gas",
        "gasPrice": "gasPrice",
        "maxFeePerGas": "maxFeePerGas",
        "maxPriorityFeePerGas": "maxPriorityFeePerGas",
        "value": "value",
    }
    for source, target in field_map.items():
        if tx.get(source) is not None:
            call[target] = tx[source]
    call["data"] = tx.get("input", "0x")
    return call


def geth_params(call: dict[str, Any]) -> list[Any]:
    return [
        call,
        "pending",
        {
            "tracer": "callTracer",
            "timeout": "1500ms",
            "tracerConfig": {"withLog": true_json()},
        },
    ]


def true_json() -> bool:
    return True


def erigon_params(call: dict[str, Any]) -> list[Any]:
    return [call, ["trace", "stateDiff"], "pending"]


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
    children = node.get("calls") or []
    flattened = [item]
    for child in children:
        if isinstance(child, dict):
            flattened.extend(flatten_geth_call(child, depth + 1))
    return flattened


def collect_geth_logs(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect callTracer logs from the root and every nested call frame."""
    logs = [item for item in node.get("logs", []) if isinstance(item, dict)]
    for child in node.get("calls") or []:
        if isinstance(child, dict):
            logs.extend(collect_geth_logs(child))
    return logs


def normalize_trace(source: str, result: Any) -> tuple[list[Any], list[Any], dict[str, Any]]:
    if source == "debug_traceCall":
        if isinstance(result, dict):
            calls = flatten_geth_call(result)
            logs = collect_geth_logs(result)
            return calls, logs, {}
        return [], [], {}
    if source == "trace_call":
        if isinstance(result, dict):
            calls = result.get("trace") if isinstance(result.get("trace"), list) else []
            state_diff = (
                result.get("stateDiff") if isinstance(result.get("stateDiff"), dict) else {}
            )
            return calls, [], state_diff
        if isinstance(result, list):
            return result, [], {}
    return [], [], {}


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


def build_bundle(
    pending_event: dict[str, Any],
    source: str,
    status: str,
    calls: list[Any],
    logs: list[Any],
    state_diff: dict[str, Any],
    trace_error: dict[str, Any] | None,
    raw_trace_ref: str | None,
) -> dict[str, Any]:
    created = now_dt()
    chain_id = pending_event["chain_id"]
    tx_hash = pending_event["tx_hash"]
    event_id = event_id_for(chain_id, tx_hash, source)
    return {
        "event_id": event_id,
        "schema_ver": "trace-bundle.v1",
        "chain_id": chain_id,
        "created_at": created.isoformat(timespec="milliseconds"),
        "observed_at": pending_event.get("seen_at") or pending_event.get("created_at"),
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


def fallback_bundle(pending_event: dict[str, Any], reason: str, errors: list[Any]) -> dict[str, Any]:
    return build_bundle(
        pending_event,
        "provider_fallback",
        "unsupported",
        [],
        [],
        {},
        {
            "code": "provider_only_trace_unavailable",
            "message": reason,
            "upstream_event_id": pending_event.get("event_id"),
            "raw_tx_status": pending_event.get("raw_tx_status"),
            "attempt_errors": errors,
        },
        None,
    )


def trace_one(
    root: Path,
    pending_event: dict[str, Any],
    geth_url: str | None,
    erigon_url: str | None,
    timeout_s: float,
    retries: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    call = pending_call_object(pending_event)
    if call is None:
        bundle = fallback_bundle(
            pending_event,
            "PendingTxEvent has no transaction object usable for trace_call.",
            [],
        )
        return bundle, {"attempts": [], "selected": "provider_fallback"}

    attempts = []
    candidates = []
    if geth_url:
        candidates.append(("debug_traceCall", geth_url, geth_params(call)))
    if erigon_url:
        candidates.append(("trace_call", erigon_url, erigon_params(call)))

    for source, url, params in candidates:
        for attempt_index in range(retries + 1):
            response, latency_ms = rpc_call(url, source, params, timeout_s)
            attempt = {
                "source": source,
                "attempt": attempt_index + 1,
                "latency_ms": round(latency_ms, 2),
                "ok": "result" in response and "error" not in response,
            }
            attempts.append(attempt)
            if "result" in response and "error" not in response:
                created = now_dt()
                raw_path = raw_trace_path(root, created, pending_event["tx_hash"], source)
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(
                    json.dumps(response["result"], indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                calls, logs, state_diff = normalize_trace(source, response["result"])
                bundle = build_bundle(
                    pending_event,
                    source,
                    "ok",
                    calls,
                    logs,
                    state_diff,
                    None,
                    str(raw_path.relative_to(root)),
                )
                return bundle, {"attempts": attempts, "selected": source}
            attempt["error"] = error_object(source, response, latency_ms)

    if attempts:
        bundle = build_bundle(
            pending_event,
            "provider_fallback",
            "failed",
            [],
            [],
            {},
            {
                "code": "trace_attempts_failed",
                "message": "All configured trace endpoints failed.",
                "upstream_event_id": pending_event.get("event_id"),
                "attempts": attempts,
            },
            None,
        )
        return bundle, {"attempts": attempts, "selected": "provider_fallback"}

    bundle = fallback_bundle(
        pending_event,
        "No Geth or Erigon trace endpoint environment variables are configured.",
        attempts,
    )
    return bundle, {"attempts": attempts, "selected": "provider_fallback"}


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors = []
    required = {
        "event_id",
        "schema_ver",
        "chain_id",
        "created_at",
        "idempotency_key",
        "tx_hash",
        "trace_source",
        "trace_status",
        "calls",
        "logs",
        "state_diff",
    }
    missing = sorted(required - set(bundle))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if bundle.get("schema_ver") != "trace-bundle.v1":
        errors.append("schema_ver must be trace-bundle.v1")
    if bundle.get("trace_status") not in {"ok", "failed", "timeout", "unsupported"}:
        errors.append("invalid trace_status")
    if not isinstance(bundle.get("calls"), list):
        errors.append("calls must be a list")
    if not isinstance(bundle.get("logs"), list):
        errors.append("logs must be a list")
    if not isinstance(bundle.get("state_diff"), dict):
        errors.append("state_diff must be an object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/replay/pending-tx.v1")
    parser.add_argument("--summary-out", default="ops/reports/pending-trace-worker.latest.json")
    parser.add_argument("--geth-url-env", default="ETH_MAIN_HTTP_URL")
    parser.add_argument("--erigon-url-env", default="ETH_BACKUP_HTTP_URL")
    parser.add_argument("--timeout-ms", type=int, default=1500)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    files = sorted((root / args.input).glob("dt=*/hour=*/*.json"))
    if args.limit is not None:
        files = files[: args.limit]

    geth_url = os.getenv(args.geth_url_env)
    erigon_url = os.getenv(args.erigon_url_env)
    timeout_s = args.timeout_ms / 1000

    written = []
    errors = []
    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    start = time.perf_counter()

    for pending_path in files:
        try:
            pending_event = json.loads(pending_path.read_text(encoding="utf-8"))
            bundle, meta = trace_one(
                root,
                pending_event,
                geth_url,
                erigon_url,
                timeout_s,
                args.retries,
            )
        except (KeyError, json.JSONDecodeError) as exc:
            errors.append({"path": str(pending_path.relative_to(root)), "errors": [str(exc)]})
            continue

        validation_errors = validate_bundle(bundle)
        if validation_errors:
            errors.append(
                {
                    "path": str(pending_path.relative_to(root)),
                    "tx_hash": pending_event.get("tx_hash"),
                    "errors": validation_errors,
                }
            )
            continue

        output_path = replay_path(root, now_dt(), bundle["event_id"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
        status_counts[bundle["trace_status"]] = status_counts.get(bundle["trace_status"], 0) + 1
        source_counts[bundle["trace_source"]] = source_counts.get(bundle["trace_source"], 0) + 1
        written.append(
            {
                "event_id": bundle["event_id"],
                "tx_hash": bundle["tx_hash"],
                "trace_source": bundle["trace_source"],
                "trace_status": bundle["trace_status"],
                "replay_path": str(output_path.relative_to(root)),
                "selected": meta["selected"],
                "attempt_count": len(meta["attempts"]),
            }
        )

    summary = {
        "checked_at": now_dt().isoformat(timespec="milliseconds"),
        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        "input": args.input,
        "pending_files_seen": len(files),
        "written_trace_bundles": len(written),
        "trace_status_counts": status_counts,
        "trace_source_counts": source_counts,
        "geth_configured": bool(geth_url),
        "erigon_configured": bool(erigon_url),
        "timeout_ms": args.timeout_ms,
        "retries": args.retries,
        "written": written,
        "errors": errors,
        "status": "ok" if written and not errors else "degraded",
    }
    out_path = root / args.summary_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
