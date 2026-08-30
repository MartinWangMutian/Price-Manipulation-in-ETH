#!/usr/bin/env python3
"""Synthetic path and record checks for trace_bundle_audit.py."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from trace_bundle_audit import audit_bundle, iter_json_files


def main() -> int:
    tx_hash = "0x" + "1" * 64
    event_id = "a" * 64
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        raw = root / "data/raw-trace/one.json"
        raw.parent.mkdir(parents=True)
        raw.write_text("[]\n", encoding="utf-8")
        bundle_path = root / f"data/replay/trace-bundle.v1/dt=2026-08-30/hour=13/{event_id}.json"
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_text("{}\n", encoding="utf-8")
        assert iter_json_files(bundle_path.parent) == [bundle_path]
        bundle = {
            "event_id": event_id,
            "schema_ver": "trace-bundle.v1",
            "chain_id": 1,
            "tx_hash": tx_hash,
            "trace_source": "trace_transaction",
            "trace_status": "ok",
            "idempotency_key": f"1:{tx_hash}:trace_transaction",
            "calls": [{}],
            "logs": [],
            "state_diff": {},
            "raw_trace_ref": str(raw.relative_to(root)),
        }
        assert audit_bundle(root, bundle_path, bundle) == []
    print("trace_bundle_audit_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
