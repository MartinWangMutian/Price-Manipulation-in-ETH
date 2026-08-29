#!/usr/bin/env python3
"""Annotate parsed trace features with protocol contract roles."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FEATURE_ENRICHER_VER = "protocol-role-enricher.v1"


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


def normalize_address(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    text = "0x" + value[2:].lower()
    if len(text) == 42:
        return text
    if len(text) == 66:
        return "0x" + text[-40:]
    return None


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def load_role_index(path: Path) -> dict[str, dict[str, Any]]:
    data = read_json(path)
    index: dict[str, dict[str, Any]] = {}
    for contract in data.get("contracts", []):
        if not isinstance(contract, dict):
            continue
        address = normalize_address(contract.get("address"))
        if address is not None:
            index[address] = contract
    return index


def role_annotation(address: str | None, role_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if address is None:
        return None
    contract = role_index.get(address)
    if contract is None:
        return None
    return {
        "address": address,
        "protocol_id": contract.get("protocol_id"),
        "category": contract.get("category"),
        "contract": contract.get("contract"),
        "roles": contract.get("roles", []),
        "graph_node_type": contract.get("graph_node_type"),
        "audit_status": contract.get("audit_status", "unknown"),
        "governance_control": contract.get("governance_control", "unknown"),
        "pause_capability": contract.get(
            "pause_capability",
            bool(contract.get("emergency_surface", False)),
        ),
        "upgradeability": contract.get("upgradeability", "unknown"),
        "risk_tier": contract.get("risk_tier", "unknown"),
        "emergency_surface": contract.get("emergency_surface", False),
    }


def build_protocol_features(parsed: dict[str, Any], role_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    call_annotations: list[dict[str, Any]] = []
    transfer_annotations: list[dict[str, Any]] = []
    matched: dict[str, dict[str, Any]] = {}

    for call in parsed.get("calls", []):
        if not isinstance(call, dict):
            continue
        for side in ("from", "to"):
            address = normalize_address(call.get(side))
            annotation = role_annotation(address, role_index)
            if annotation is None:
                continue
            item = {"call_ordinal": call.get("ordinal"), "side": side, **annotation}
            call_annotations.append(item)
            matched[annotation["address"]] = annotation

    for transfer in parsed.get("token_transfers", []):
        if not isinstance(transfer, dict):
            continue
        for side in ("token", "from", "to", "operator"):
            address = normalize_address(transfer.get(side))
            annotation = role_annotation(address, role_index)
            if annotation is None:
                continue
            item = {
                "transfer_event_id": transfer.get("event_id"),
                "side": side,
                **annotation,
            }
            transfer_annotations.append(item)
            matched[annotation["address"]] = annotation

    missing_flags = list(parsed.get("feature_missing_flags", []))
    if not matched:
        missing_flags.append("no_protocol_role_matches")
    if not parsed.get("calls") and not parsed.get("token_transfers"):
        missing_flags.append("insufficient_trace_context_for_protocol_roles")

    event_id = hashlib.sha256(
        f"protocol-features.v1:{parsed['idempotency_key']}".encode("utf-8")
    ).hexdigest()
    return {
        "event_id": event_id,
        "schema_ver": "protocol-features.v1",
        "chain_id": parsed["chain_id"],
        "created_at": now_iso(),
        "idempotency_key": f"{parsed['idempotency_key']}:protocol-features.v1",
        "source_parsed_event_id": parsed["event_id"],
        "source_parsed_idempotency_key": parsed["idempotency_key"],
        "feature_enricher_ver": FEATURE_ENRICHER_VER,
        "tx_hash": parsed["tx_hash"],
        "matched_protocol_roles": sorted(matched.values(), key=lambda item: item["address"]),
        "call_protocol_annotations": call_annotations,
        "transfer_protocol_annotations": transfer_annotations,
        "feature_missing_flags": sorted(set(missing_flags)),
    }


def replay_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "replay"
        / "protocol-features.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Annotate parsed traces with protocol roles.")
    parser.add_argument("--input", default="data/replay/parsed-trace.v1")
    parser.add_argument("--roles", default="config/protocol_roles.json")
    parser.add_argument("--out", default="ops/reports/protocol-role-enricher.latest.json")
    parser.add_argument("--write-replay", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    role_index = load_role_index(root / args.roles)
    seen_input_keys: set[str] = set()
    records: list[dict[str, Any]] = []
    skipped_duplicates = 0
    errors: list[dict[str, Any]] = []

    for path in iter_json_files(root / args.input):
        try:
            parsed = read_json(path)
            key = parsed.get("idempotency_key")
            if not isinstance(key, str):
                errors.append({"path": str(path), "error": "missing idempotency_key"})
                continue
            if key in seen_input_keys:
                skipped_duplicates += 1
                continue
            seen_input_keys.add(key)
            record = build_protocol_features(parsed, role_index)
            records.append(record)
            if args.write_replay:
                write_json(replay_output_path(root, record), record)
        except Exception as exc:  # noqa: BLE001 - keep audit-style report complete.
            errors.append({"path": str(path), "error": str(exc)})

    role_counts = Counter()
    protocol_counts = Counter()
    missing_flags = Counter()
    matched_records = 0
    for record in records:
        if record["matched_protocol_roles"]:
            matched_records += 1
        for annotation in record["matched_protocol_roles"]:
            protocol_counts[annotation.get("protocol_id", "unknown")] += 1
            for role in annotation.get("roles", []):
                role_counts[role] += 1
        for flag in record["feature_missing_flags"]:
            missing_flags[flag] += 1

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "input": args.input,
        "role_contracts_loaded": len(role_index),
        "files_seen": len(iter_json_files(root / args.input)),
        "unique_parsed_records": len(seen_input_keys),
        "skipped_duplicate_parsed_records": skipped_duplicates,
        "protocol_feature_records": len(records),
        "records_with_role_matches": matched_records,
        "protocol_counts": dict(sorted(protocol_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "feature_missing_flags": dict(sorted(missing_flags.items())),
        "write_replay": args.write_replay,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
