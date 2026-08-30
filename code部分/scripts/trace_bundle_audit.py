#!/usr/bin/env python3
"""P2-C TraceBundle audit.

This audit checks TraceBundle field validity, normalized replay persistence,
raw trace references for successful traces, and downstream idempotency after
replay duplicates are deduped.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_SOURCES = {
    "debug_traceCall",
    "trace_call",
    "debug_traceTransaction",
    "trace_transaction",
    "provider_fallback",
    "none",
}
VALID_STATUSES = {"ok", "failed", "timeout", "unsupported"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_json_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.json"))


def audit_bundle(root: Path, path: Path, bundle: dict[str, Any]) -> list[str]:
    errors = []
    if bundle.get("schema_ver") != "trace-bundle.v1":
        errors.append("invalid schema_ver")

    tx_hash = bundle.get("tx_hash")
    if not (
        isinstance(tx_hash, str)
        and tx_hash.startswith("0x")
        and len(tx_hash) == 66
    ):
        errors.append("invalid tx_hash")

    source = bundle.get("trace_source")
    if source not in VALID_SOURCES:
        errors.append("invalid trace_source")

    status = bundle.get("trace_status")
    if status not in VALID_STATUSES:
        errors.append("invalid trace_status")

    for field in ("calls", "logs"):
        if not isinstance(bundle.get(field), list):
            errors.append(f"{field} must be list")
    if not isinstance(bundle.get("state_diff"), dict):
        errors.append("state_diff must be object")

    if path.stem != bundle.get("event_id"):
        errors.append("file name does not match event_id")

    if tx_hash and source:
        expected_key = f"1:{tx_hash}:{source}"
        if bundle.get("idempotency_key") != expected_key:
            errors.append("idempotency_key mismatch")

    raw_ref = bundle.get("raw_trace_ref")
    if status == "ok":
        if not raw_ref:
            errors.append("ok trace must have raw_trace_ref")
        elif not (root / raw_ref).exists():
            errors.append("raw_trace_ref target missing")
    elif raw_ref is not None:
        errors.append("non-ok trace should not have raw_trace_ref")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/replay/trace-bundle.v1")
    parser.add_argument("--out", default="ops/reports/trace-bundle-audit.latest.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    files = iter_json_files(root / args.input)
    errors = []
    keys = []
    status_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    raw_trace_refs = 0
    normalized_trace_files = 0

    for path in files:
        try:
            bundle = load_json(path)
        except json.JSONDecodeError as exc:
            errors.append({"path": str(path.relative_to(root)), "errors": [str(exc)]})
            continue

        bundle_errors = audit_bundle(root, path, bundle)
        if bundle_errors:
            errors.append(
                {
                    "path": str(path.relative_to(root)),
                    "event_id": bundle.get("event_id"),
                    "errors": bundle_errors,
                }
            )
            continue

        normalized_trace_files += 1
        keys.append(bundle["idempotency_key"])
        status_counts[bundle["trace_status"]] += 1
        source_counts[bundle["trace_source"]] += 1
        if bundle.get("raw_trace_ref"):
            raw_trace_refs += 1

    key_counts = Counter(keys)
    duplicate_keys = sorted(key for key, count in key_counts.items() if count > 1)
    summary = {
        "checked_at": now_iso(),
        "input": args.input,
        "files_seen": len(files),
        "normalized_trace_files": normalized_trace_files,
        "raw_trace_refs": raw_trace_refs,
        "trace_status_counts": dict(sorted(status_counts.items())),
        "trace_source_counts": dict(sorted(source_counts.items())),
        "unique_idempotency_keys": len(key_counts),
        "duplicate_idempotency_keys": duplicate_keys,
        "deduped_downstream_events": len(key_counts),
        "errors": errors,
        "status": "ok" if normalized_trace_files and not errors else "degraded",
        "provider_only_note": (
            "raw_trace_refs is expected to be 0 when all traces are "
            "provider_fallback/unsupported."
        ),
    }

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
