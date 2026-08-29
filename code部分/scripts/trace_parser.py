#!/usr/bin/env python3
"""Parse TraceBundle replay records into normalized transfer and call features."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ERC1155_SINGLE_TOPIC = "0xc3d58168c5ae7397731d063d5bbf3d6d37f186a5b44a5fbf0aecd7d43b1c7a"
ERC1155_BATCH_TOPIC = "0x4a39dc06d4c0dbc64b70b2b9b850f3c9e70e74a5d2bd5cc664fa352f4aa3a08f"
ERROR_STRING_SELECTOR = "0x08c379a0"
PARSER_VER = "trace-parser.v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def normalize_hex(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    return "0x" + value[2:].lower()


def normalize_address(value: Any) -> str | None:
    text = normalize_hex(value)
    if text is None:
        return None
    if len(text) == 42:
        return text
    if len(text) == 66:
        return "0x" + text[-40:]
    return None


def hex_to_int(value: Any) -> int | None:
    text = normalize_hex(value)
    if text is None:
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None


def clean_data_words(data: Any) -> list[str]:
    text = normalize_hex(data)
    if text is None:
        return []
    body = text[2:]
    if not body:
        return []
    if len(body) % 64 != 0:
        body = body.rjust(((len(body) // 64) + 1) * 64, "0")
    return ["0x" + body[i : i + 64] for i in range(0, len(body), 64)]


def amount_norm(amount_raw: str | None, decimals: int | None) -> str | None:
    if amount_raw is None or decimals is None:
        return None
    value = Decimal(amount_raw) / (Decimal(10) ** Decimal(decimals))
    return format(value.normalize(), "f")


def metadata_for(token: str | None, cache: dict[str, Any]) -> dict[str, Any]:
    if token is None:
        return {}
    item = cache.get(token.lower())
    return item if isinstance(item, dict) else {}


def transfer_event_id(tx_hash: str, log_index: int | None, token: str | None, ordinal: int) -> str:
    seed = f"transfer:{tx_hash}:{log_index}:{token}:{ordinal}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def parse_transfer_log(log: dict[str, Any], tx_hash: str, metadata_cache: dict[str, Any]) -> list[dict[str, Any]]:
    topics = log.get("topics")
    if not isinstance(topics, list) or not topics:
        return []
    topic0 = normalize_hex(topics[0])
    token = normalize_address(log.get("address"))
    log_index = hex_to_int(log.get("logIndex"))
    if log_index is None and isinstance(log.get("log_index"), int):
        log_index = log["log_index"]

    if topic0 == TRANSFER_TOPIC:
        if len(topics) < 3:
            return []
        token_meta = metadata_for(token, metadata_cache)
        asset_type = token_meta.get("asset_type")
        sender = normalize_address(topics[1])
        receiver = normalize_address(topics[2])
        if len(topics) >= 4 or asset_type == "erc721":
            token_id = hex_to_int(topics[3]) if len(topics) >= 4 else None
            return [
                {
                    "event_id": transfer_event_id(tx_hash, log_index, token, 0),
                    "standard": "erc721",
                    "token": token,
                    "symbol": token_meta.get("symbol"),
                    "decimals": token_meta.get("decimals"),
                    "from": sender,
                    "to": receiver,
                    "token_id": str(token_id) if token_id is not None else None,
                    "amount_raw": "1",
                    "amount_norm": "1",
                    "log_index": log_index,
                }
            ]
        words = clean_data_words(log.get("data"))
        amount_int = hex_to_int(words[0]) if words else None
        decimals = token_meta.get("decimals")
        decimals_int = decimals if isinstance(decimals, int) else None
        amount_raw = str(amount_int) if amount_int is not None else None
        return [
            {
                "event_id": transfer_event_id(tx_hash, log_index, token, 0),
                "standard": "erc20",
                "token": token,
                "symbol": token_meta.get("symbol"),
                "decimals": decimals_int,
                "from": sender,
                "to": receiver,
                "token_id": None,
                "amount_raw": amount_raw,
                "amount_norm": amount_norm(amount_raw, decimals_int),
                "log_index": log_index,
            }
        ]

    if topic0 == ERC1155_SINGLE_TOPIC:
        if len(topics) < 4:
            return []
        words = clean_data_words(log.get("data"))
        if len(words) < 2:
            return []
        token_id = hex_to_int(words[0])
        amount_int = hex_to_int(words[1])
        return [
            {
                "event_id": transfer_event_id(tx_hash, log_index, token, 0),
                "standard": "erc1155",
                "token": token,
                "symbol": metadata_for(token, metadata_cache).get("symbol"),
                "decimals": None,
                "operator": normalize_address(topics[1]),
                "from": normalize_address(topics[2]),
                "to": normalize_address(topics[3]),
                "token_id": str(token_id) if token_id is not None else None,
                "amount_raw": str(amount_int) if amount_int is not None else None,
                "amount_norm": str(amount_int) if amount_int is not None else None,
                "log_index": log_index,
            }
        ]

    if topic0 == ERC1155_BATCH_TOPIC:
        return parse_erc1155_batch(log, tx_hash, token, log_index, metadata_cache)

    return []


def parse_erc1155_batch(
    log: dict[str, Any],
    tx_hash: str,
    token: str | None,
    log_index: int | None,
    metadata_cache: dict[str, Any],
) -> list[dict[str, Any]]:
    topics = log.get("topics")
    if not isinstance(topics, list) or len(topics) < 4:
        return []
    words = clean_data_words(log.get("data"))
    if len(words) < 4:
        return []
    id_offset = hex_to_int(words[0])
    value_offset = hex_to_int(words[1])
    if id_offset is None or value_offset is None:
        return []
    id_start = id_offset // 32
    value_start = value_offset // 32
    if id_start >= len(words) or value_start >= len(words):
        return []
    id_count = hex_to_int(words[id_start]) or 0
    value_count = hex_to_int(words[value_start]) or 0
    count = min(id_count, value_count)
    transfers: list[dict[str, Any]] = []
    token_meta = metadata_for(token, metadata_cache)
    for idx in range(count):
        id_word_index = id_start + 1 + idx
        value_word_index = value_start + 1 + idx
        if id_word_index >= len(words) or value_word_index >= len(words):
            break
        token_id = hex_to_int(words[id_word_index])
        amount_int = hex_to_int(words[value_word_index])
        transfers.append(
            {
                "event_id": transfer_event_id(tx_hash, log_index, token, idx),
                "standard": "erc1155",
                "token": token,
                "symbol": token_meta.get("symbol"),
                "decimals": None,
                "operator": normalize_address(topics[1]),
                "from": normalize_address(topics[2]),
                "to": normalize_address(topics[3]),
                "token_id": str(token_id) if token_id is not None else None,
                "amount_raw": str(amount_int) if amount_int is not None else None,
                "amount_norm": str(amount_int) if amount_int is not None else None,
                "log_index": log_index,
                "batch_index": idx,
            }
        )
    return transfers


def decode_revert_reason(output: Any, error: Any) -> str | None:
    if isinstance(error, str) and error:
        return error
    text = normalize_hex(output)
    if text is None or not text.startswith(ERROR_STRING_SELECTOR):
        return None
    words = clean_data_words("0x" + text[10:])
    if len(words) < 2:
        return None
    length = hex_to_int(words[1]) or 0
    raw = "".join(word[2:] for word in words[2:])
    try:
        return bytes.fromhex(raw[: length * 2]).decode("utf-8", errors="replace")
    except ValueError:
        return None


def call_input(call: dict[str, Any]) -> str | None:
    for key in ("input", "data"):
        value = normalize_hex(call.get(key))
        if value is not None:
            return value
    action = call.get("action")
    if isinstance(action, dict):
        return normalize_hex(action.get("input"))
    return None


def call_depth(call: dict[str, Any]) -> int:
    depth = call.get("depth")
    if isinstance(depth, int):
        return depth
    trace_address = call.get("traceAddress")
    if isinstance(trace_address, list):
        return len(trace_address)
    return 0


def call_type(call: dict[str, Any]) -> str | None:
    value = call.get("type")
    if isinstance(value, str):
        return value
    action = call.get("action")
    if isinstance(action, dict) and isinstance(action.get("callType"), str):
        return action["callType"]
    return None


def call_success(call: dict[str, Any]) -> bool:
    if call.get("error"):
        return False
    result = call.get("result")
    if isinstance(result, dict) and result.get("error"):
        return False
    return True


def parse_call(call: dict[str, Any], selector_dict: dict[str, Any], ordinal: int) -> dict[str, Any]:
    input_value = call_input(call)
    selector = input_value[:10] if input_value and len(input_value) >= 10 else None
    selector_meta = selector_dict.get(selector, {}) if selector else {}
    result = call.get("result") if isinstance(call.get("result"), dict) else {}
    output = call.get("output", result.get("output"))
    error = call.get("error", result.get("error"))
    action = call.get("action") if isinstance(call.get("action"), dict) else {}
    parsed_call_type = call_type(call)
    recipient = normalize_address(call.get("to", action.get("to")))
    if recipient is None and str(parsed_call_type or "").lower() in {"create", "create2"}:
        recipient = normalize_address(result.get("address"))
    return {
        "ordinal": ordinal,
        "depth": call_depth(call),
        "type": parsed_call_type,
        "from": normalize_address(call.get("from", action.get("from"))),
        "to": recipient,
        "value": str(hex_to_int(call.get("value", action.get("value"))) or 0),
        "function_selector": selector,
        "function_signature": selector_meta.get("signature"),
        "function_name": selector_meta.get("name"),
        "protocol_hint": selector_meta.get("protocol"),
        "success": call_success(call),
        "revert_reason": decode_revert_reason(output, error),
    }


def parse_trace_bundle(
    bundle: dict[str, Any],
    selector_dict: dict[str, Any],
    metadata_cache: dict[str, Any],
) -> dict[str, Any]:
    tx_hash = bundle["tx_hash"]
    logs = bundle.get("logs") if isinstance(bundle.get("logs"), list) else []
    calls = bundle.get("calls") if isinstance(bundle.get("calls"), list) else []
    transfers: list[dict[str, Any]] = []
    for log in logs:
        if isinstance(log, dict):
            transfers.extend(parse_transfer_log(log, tx_hash, metadata_cache))
    parsed_calls = [
        parse_call(call, selector_dict, idx)
        for idx, call in enumerate(calls)
        if isinstance(call, dict)
    ]
    missing_flags: list[str] = []
    if bundle.get("trace_status") != "ok":
        missing_flags.append(f"trace_{bundle.get('trace_status', 'unknown')}")
    if not logs:
        missing_flags.append("no_logs")
    if not calls:
        missing_flags.append("no_calls")
    if transfers and any(item.get("amount_norm") is None for item in transfers):
        missing_flags.append("token_decimals_missing")
    event_id = hashlib.sha256(
        f"parsed-trace.v1:{bundle['idempotency_key']}".encode("utf-8")
    ).hexdigest()
    return {
        "event_id": event_id,
        "schema_ver": "parsed-trace.v1",
        "chain_id": bundle["chain_id"],
        "created_at": now_iso(),
        "observed_at": bundle.get("observed_at") or bundle.get("created_at"),
        "idempotency_key": f"{bundle['idempotency_key']}:parsed-trace.v1",
        "source_trace_event_id": bundle["event_id"],
        "source_trace_idempotency_key": bundle["idempotency_key"],
        "tx_hash": tx_hash,
        "trace_source": bundle.get("trace_source"),
        "trace_status": bundle.get("trace_status"),
        "raw_trace_ref": bundle.get("raw_trace_ref"),
        "parser_ver": PARSER_VER,
        "token_transfers": transfers,
        "calls": parsed_calls,
        "feature_missing_flags": sorted(set(missing_flags)),
    }


def replay_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "replay"
        / "parsed-trace.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse trace bundle replay records.")
    parser.add_argument("--input", default="data/replay/trace-bundle.v1")
    parser.add_argument("--selector-dict", default="config/selector_dictionary.json")
    parser.add_argument(
        "--token-metadata", default="config/token_metadata_cache.example.json"
    )
    parser.add_argument("--out", default="ops/reports/trace-parser.latest.json")
    parser.add_argument("--write-replay", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    selector_dict = load_optional_json(root / args.selector_dict)
    metadata_cache = load_optional_json(root / args.token_metadata)
    input_path = root / args.input

    seen_input_keys: set[str] = set()
    parsed_records: list[dict[str, Any]] = []
    skipped_duplicates = 0
    errors: list[dict[str, Any]] = []
    for path in iter_json_files(input_path):
        try:
            bundle = read_json(path)
            key = bundle.get("idempotency_key")
            if not isinstance(key, str):
                errors.append({"path": str(path), "error": "missing idempotency_key"})
                continue
            if key in seen_input_keys:
                skipped_duplicates += 1
                continue
            seen_input_keys.add(key)
            parsed = parse_trace_bundle(bundle, selector_dict, metadata_cache)
            parsed_records.append(parsed)
            if args.write_replay:
                write_json(replay_output_path(root, parsed), parsed)
        except Exception as exc:  # noqa: BLE001 - audit report should keep scanning.
            errors.append({"path": str(path), "error": str(exc)})

    transfer_counts = Counter()
    call_success_counts = Counter()
    missing_flags = Counter()
    for record in parsed_records:
        for transfer in record["token_transfers"]:
            transfer_counts[transfer.get("standard", "unknown")] += 1
        for call in record["calls"]:
            call_success_counts["success" if call.get("success") else "failed"] += 1
        for flag in record["feature_missing_flags"]:
            missing_flags[flag] += 1

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "input": args.input,
        "files_seen": len(iter_json_files(input_path)),
        "unique_trace_bundles": len(seen_input_keys),
        "skipped_duplicate_trace_bundles": skipped_duplicates,
        "parsed_records": len(parsed_records),
        "write_replay": args.write_replay,
        "token_transfer_counts": dict(sorted(transfer_counts.items())),
        "calls": {
            "total": sum(call_success_counts.values()),
            "success": call_success_counts.get("success", 0),
            "failed": call_success_counts.get("failed", 0),
        },
        "feature_missing_flags": dict(sorted(missing_flags.items())),
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
