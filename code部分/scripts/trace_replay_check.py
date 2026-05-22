#!/usr/bin/env python3
"""Validate trace-bundle replay records."""

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
    "trace_source",
    "trace_status",
    "calls",
    "logs",
    "state_diff",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def validate_bundle(path: Path, bundle: dict[str, Any]) -> list[str]:
    errors = []
    missing = sorted(REQUIRED_FIELDS - set(bundle))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if bundle.get("schema_ver") != "trace-bundle.v1":
        errors.append("schema_ver must be trace-bundle.v1")
    if bundle.get("chain_id") != 1:
        errors.append("chain_id must be 1")
    tx_hash = bundle.get("tx_hash")
    if not (
        isinstance(tx_hash, str)
        and tx_hash.startswith("0x")
        and len(tx_hash) == 66
    ):
        errors.append("tx_hash must be a 32-byte hex string")
    if path.stem != bundle.get("event_id"):
        errors.append("file name must match event_id")
    if bundle.get("trace_status") not in {"ok", "failed", "timeout", "unsupported"}:
        errors.append("invalid trace_status")
    for field in ("calls", "logs"):
        if not isinstance(bundle.get(field), list):
            errors.append(f"{field} must be a list")
    if not isinstance(bundle.get("state_diff"), dict):
        errors.append("state_diff must be an object")
    source = bundle.get("trace_source")
    if tx_hash and source:
        expected = f"1:{tx_hash}:{source}"
        if bundle.get("idempotency_key") != expected:
            errors.append(f"idempotency_key mismatch: expected {expected}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/replay/trace-bundle.v1",
        help="trace-bundle replay root",
    )
    parser.add_argument(
        "--out",
        default="ops/reports/trace-replay-check.latest.json",
        help="summary report path",
    )
    parser.add_argument(
        "--allow-replay-duplicates",
        action="store_true",
        help="treat duplicate idempotency keys as replay duplicates, not errors",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    files = sorted((root / args.input).glob("dt=*/hour=*/*.json"))
    errors: list[dict[str, Any]] = []
    keys: list[str] = []

    for path in files:
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append({"path": str(path.relative_to(root)), "errors": [str(exc)]})
            continue
        validation_errors = validate_bundle(path, bundle)
        if validation_errors:
            errors.append(
                {
                    "path": str(path.relative_to(root)),
                    "event_id": bundle.get("event_id"),
                    "errors": validation_errors,
                }
            )
            continue
        keys.append(bundle["idempotency_key"])

    counts = Counter(keys)
    duplicate_keys = sorted(key for key, count in counts.items() if count > 1)
    summary = {
        "checked_at": now_iso(),
        "input": args.input,
        "files_seen": len(files),
        "valid_events": len(keys),
        "unique_idempotency_keys": len(counts),
        "deduped_downstream_events": len(counts),
        "duplicate_idempotency_keys": duplicate_keys,
        "allow_replay_duplicates": args.allow_replay_duplicates,
        "errors": errors,
        "status": "ok"
        if keys and not errors and (not duplicate_keys or args.allow_replay_duplicates)
        else "degraded",
    }
    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
