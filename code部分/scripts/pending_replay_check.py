#!/usr/bin/env python3
"""Validate and deduplicate pending transaction replay records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def validate_event(path: Path, event: dict[str, Any]) -> list[str]:
    errors = []
    missing = sorted(REQUIRED_FIELDS - set(event))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if event.get("schema_ver") != "pending-tx.v1":
        errors.append("schema_ver must be pending-tx.v1")
    if event.get("chain_id") != 1:
        errors.append("chain_id must be 1")
    tx_hash = event.get("tx_hash")
    if not (
        isinstance(tx_hash, str)
        and tx_hash.startswith("0x")
        and len(tx_hash) == 66
    ):
        errors.append("tx_hash must be a 32-byte hex string")
    source = event.get("source")
    if tx_hash and source:
        expected = f"1:{tx_hash}:{source}"
        if event.get("idempotency_key") != expected:
            errors.append(f"idempotency_key mismatch: expected {expected}")
    if path.stem != event.get("event_id"):
        errors.append("file name must match event_id")
    if event.get("raw_tx_status") not in {
        "available",
        "unavailable_from_provider",
        "not_found",
        "error",
    }:
        errors.append("invalid raw_tx_status")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/replay/pending-tx.v1",
        help="pending-tx replay root",
    )
    parser.add_argument(
        "--out",
        default="ops/reports/pending-replay-check.latest.json",
        help="summary report path",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    input_root = root / args.input
    files = sorted(input_root.glob("dt=*/hour=*/*.json"))
    errors: list[dict[str, Any]] = []
    events: list[dict[str, str]] = []
    idempotency_keys: list[str] = []

    for path in files:
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append({"path": str(path.relative_to(root)), "errors": [str(exc)]})
            continue
        validation_errors = validate_event(path, event)
        if validation_errors:
            errors.append(
                {
                    "path": str(path.relative_to(root)),
                    "event_id": event.get("event_id"),
                    "errors": validation_errors,
                }
            )
            continue
        idempotency_keys.append(event["idempotency_key"])
        events.append(
            {
                "event_id": event["event_id"],
                "tx_hash": event["tx_hash"],
                "idempotency_key": event["idempotency_key"],
            }
        )

    counts = Counter(idempotency_keys)
    duplicate_keys = sorted(key for key, count in counts.items() if count > 1)
    summary = {
        "checked_at": now_iso(),
        "input": args.input,
        "files_seen": len(files),
        "valid_events": len(events),
        "unique_idempotency_keys": len(counts),
        "duplicate_idempotency_keys": duplicate_keys,
        "errors": errors,
        "status": "ok" if not errors and not duplicate_keys and events else "degraded",
    }
    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
