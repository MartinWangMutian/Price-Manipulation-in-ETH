#!/usr/bin/env python3
"""Build a secret-free hash manifest for local-only raw historical traces."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def queue_hashes(paths: list[Path]) -> set[str]:
    hashes: set[str] = set()
    for path in paths:
        payload = read_json(path)
        hashes.update(str(item["tx_hash"]).lower() for item in payload.get("items", []))
    return hashes


def build_manifest(root: Path, bundle_root: Path, expected_hashes: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for path in sorted(bundle_root.rglob("*.json")):
        bundle = read_json(path)
        tx_hash = str(bundle.get("tx_hash", "")).lower()
        if tx_hash not in expected_hashes or bundle.get("trace_source") != "trace_transaction":
            continue
        if bundle.get("trace_status") != "ok":
            errors.append(f"non-ok bundle for {tx_hash}")
            continue
        if tx_hash in seen:
            errors.append(f"duplicate trace_transaction bundle for {tx_hash}")
            continue
        raw_ref = bundle.get("raw_trace_ref")
        raw_path = root / str(raw_ref)
        if not isinstance(raw_ref, str) or not raw_path.exists():
            errors.append(f"missing raw trace for {tx_hash}")
            continue
        seen.add(tx_hash)
        entries.append(
            {
                "tx_hash": tx_hash,
                "trace_source": "trace_transaction",
                "bundle_ref": str(path.relative_to(root)),
                "raw_trace_ref": raw_ref,
                "raw_bytes": raw_path.stat().st_size,
                "raw_sha256": sha256_file(raw_path),
            }
        )
    missing = sorted(expected_hashes - seen)
    errors.extend(f"missing successful trace_transaction bundle for {tx_hash}" for tx_hash in missing)
    return sorted(entries, key=lambda item: item["tx_hash"]), errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Hash local raw traces without committing their content.")
    parser.add_argument("--queue", action="append", required=True)
    parser.add_argument("--bundles", default="data/replay/trace-bundle.v1")
    parser.add_argument("--out", default="data/training/raw-trace-manifest.stage2.v1.json")
    parser.add_argument("--report", default="ops/reports/raw-trace-manifest.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    expected = queue_hashes([root / path for path in args.queue])
    entries, errors = build_manifest(root, root / args.bundles, expected)
    payload = {
        "schema_ver": "raw-trace-manifest.v1",
        "created_at": now_iso(),
        "raw_content_committed": False,
        "expected_transactions": len(expected),
        "entries": entries,
    }
    write_json(root / args.out, payload)
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors and len(entries) == len(expected) else "failed",
        "expected_transactions": len(expected),
        "manifest_entries": len(entries),
        "raw_bytes": sum(item["raw_bytes"] for item in entries),
        "errors": errors,
        "out": args.out,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
