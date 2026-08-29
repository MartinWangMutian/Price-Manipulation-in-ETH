#!/usr/bin/env python3
"""Build 5m address and 1h protocol context windows for graph construction."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_address(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    text = "0x" + value[2:].lower()
    if len(text) == 42:
        return text
    if len(text) == 66:
        return "0x" + text[-40:]
    return None


def load_protocol_features(root: Path) -> dict[str, dict[str, Any]]:
    features = {}
    for path in iter_json_files(root):
        payload = read_json(path)
        key = payload.get("source_parsed_idempotency_key")
        if isinstance(key, str):
            features[key] = payload
    return features


def addresses_for(parsed: dict[str, Any]) -> set[str]:
    addresses: set[str] = set()
    for call in parsed.get("calls", []):
        if isinstance(call, dict):
            for side in ("from", "to"):
                address = normalize_address(call.get(side))
                if address:
                    addresses.add(address)
    for transfer in parsed.get("token_transfers", []):
        if isinstance(transfer, dict):
            for side in ("from", "to", "operator"):
                address = normalize_address(transfer.get(side))
                if address:
                    addresses.add(address)
    return addresses


def initiator_for(parsed: dict[str, Any]) -> str | None:
    calls = [call for call in parsed.get("calls", []) if isinstance(call, dict)]
    if calls:
        first = min(calls, key=lambda call: call.get("ordinal", call.get("depth", 0)))
        return normalize_address(first.get("from"))
    transfers = [transfer for transfer in parsed.get("token_transfers", []) if isinstance(transfer, dict)]
    if transfers:
        return normalize_address(transfers[0].get("from"))
    return None


def assets_for(parsed: dict[str, Any]) -> set[str]:
    assets: set[str] = set()
    for transfer in parsed.get("token_transfers", []):
        if isinstance(transfer, dict):
            token = normalize_address(transfer.get("token"))
            if token:
                assets.add(token)
    return assets


def protocol_ids_for(protocol_features: dict[str, Any]) -> set[str]:
    protocol_ids: set[str] = set()
    for key in ("matched_protocol_roles", "call_protocol_annotations", "transfer_protocol_annotations"):
        value = protocol_features.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("protocol_id"), str):
                protocol_ids.add(item["protocol_id"])
    return protocol_ids


def compact_record(parsed: dict[str, Any], protocol_features: dict[str, Any]) -> dict[str, Any] | None:
    created_at = parse_time(parsed.get("observed_at")) or parse_time(parsed.get("created_at"))
    if created_at is None:
        return None
    return {
        "tx_hash": parsed.get("tx_hash"),
        "created_at": created_at,
        "addresses": addresses_for(parsed),
        "initiator": initiator_for(parsed),
        "assets": assets_for(parsed),
        "protocol_ids": protocol_ids_for(protocol_features),
    }


def build_address_records(current: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    same_initiator = [
        item for item in history
        if current.get("initiator") and item.get("initiator") == current.get("initiator")
    ]
    if same_initiator:
        records.append(summary_record("same_initiator", ADDRESS_SUBJECT(current), same_initiator))
    same_counterparty = [
        item for item in history
        if current["addresses"] and item["addresses"] & current["addresses"]
    ]
    if same_counterparty:
        records.append(summary_record("same_counterparty", ADDRESS_SUBJECT(current), same_counterparty))
    same_asset = [
        item for item in history
        if current["assets"] and item["assets"] & current["assets"]
    ]
    if same_asset:
        records.append(summary_record("same_asset", ADDRESS_SUBJECT(current), same_asset))
    return records


def ADDRESS_SUBJECT(record: dict[str, Any]) -> str | None:
    return record.get("initiator") or next(iter(record.get("addresses") or []), None)


def summary_record(relation_type: str, address: str | None, history: list[dict[str, Any]]) -> dict[str, Any]:
    last_seen = max(item["created_at"] for item in history)
    return {
        "address": address,
        "relation_type": relation_type,
        "count": len(history),
        "last_seen_at": last_seen.isoformat(timespec="milliseconds"),
    }


def build_protocol_records(current: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter()
    last_seen: dict[str, datetime] = {}
    for item in history:
        for protocol_id in current["protocol_ids"] & item["protocol_ids"]:
            counts[protocol_id] += 1
            last_seen[protocol_id] = max(last_seen.get(protocol_id, item["created_at"]), item["created_at"])
    records = []
    for protocol_id, count in sorted(counts.items()):
        relation_type = "volume_spike" if count >= 10 else "recent_protocol_touch"
        records.append(
            {
                "protocol_id": protocol_id,
                "relation_type": relation_type,
                "count": count,
                "last_seen_at": last_seen[protocol_id].isoformat(timespec="milliseconds"),
            }
        )
    return records


def build_contexts(records: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    address_by_tx: dict[str, list[dict[str, Any]]] = defaultdict(list)
    protocol_by_tx: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ordered = sorted(records, key=lambda item: item["created_at"])
    for idx, current in enumerate(ordered):
        tx_hash = str(current["tx_hash"]).lower()
        address_since = current["created_at"] - timedelta(minutes=5)
        protocol_since = current["created_at"] - timedelta(hours=1)
        address_history = [
            item for item in ordered[:idx]
            if item["created_at"] >= address_since
        ]
        protocol_history = [
            item for item in ordered[:idx]
            if item["created_at"] >= protocol_since
        ]
        address_by_tx[tx_hash] = build_address_records(current, address_history)
        protocol_by_tx[tx_hash] = build_protocol_records(current, protocol_history)
    return dict(address_by_tx), dict(protocol_by_tx)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build context window files for cash-flow graphs.")
    parser.add_argument("--parsed-input", default="data/replay/parsed-trace.v1")
    parser.add_argument("--protocol-features", default="data/replay/protocol-features.v1")
    parser.add_argument("--address-out", default="data/context/address-context.v1.json")
    parser.add_argument("--protocol-out", default="data/context/protocol-context.v1.json")
    parser.add_argument("--report", default="ops/reports/context-window-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    protocol_index = load_protocol_features(root / args.protocol_features)
    records = []
    for path in iter_json_files(root / args.parsed_input):
        parsed = read_json(path)
        key = parsed.get("idempotency_key")
        if not isinstance(key, str):
            continue
        record = compact_record(parsed, protocol_index.get(key, {}))
        if record is not None and isinstance(record.get("tx_hash"), str):
            records.append(record)
    address_by_tx, protocol_by_tx = build_contexts(records)
    address_context = {
        "schema_ver": "address-context.v1",
        "window": "5m-address",
        "created_at": now_iso(),
        "contexts_by_tx": address_by_tx,
    }
    protocol_context = {
        "schema_ver": "protocol-context.v1",
        "window": "1h-protocol",
        "created_at": now_iso(),
        "contexts_by_tx": protocol_by_tx,
    }
    write_json(root / args.address_out, address_context)
    write_json(root / args.protocol_out, protocol_context)
    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "parsed_records": len(records),
        "address_context_records": sum(len(items) for items in address_by_tx.values()),
        "protocol_context_records": sum(len(items) for items in protocol_by_tx.values()),
        "address_out": args.address_out,
        "protocol_out": args.protocol_out,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
