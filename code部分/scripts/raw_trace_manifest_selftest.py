#!/usr/bin/env python3
"""Synthetic checks for raw_trace_manifest.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import raw_trace_manifest as manifest


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tx_hash = "0x" + "12" * 32
        raw = root / "data/raw.json"
        raw.parent.mkdir(parents=True)
        raw.write_text("[]\n", encoding="utf-8")
        bundle_dir = root / "bundles"
        bundle_dir.mkdir()
        bundle = {
            "tx_hash": tx_hash,
            "trace_source": "trace_transaction",
            "trace_status": "ok",
            "raw_trace_ref": "data/raw.json",
        }
        (bundle_dir / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        entries, errors = manifest.build_manifest(root, bundle_dir, {tx_hash})
        assert not errors, errors
        assert len(entries) == 1, entries
        assert entries[0]["raw_sha256"] == manifest.sha256_file(raw), entries
    print("raw_trace_manifest_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
