#!/usr/bin/env python3
"""Dependency-free checks for deterministic training runtime helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from training_runtime import canonical_hash, locked_requirements, normalize_package_name


def main() -> int:
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
    assert normalize_package_name("Torch_Geometric") == "torch-geometric"
    with tempfile.TemporaryDirectory() as directory:
        lock = Path(directory) / "requirements.lock.txt"
        lock.write_text("# comment\ntorch==2.13.0\ntorch_geometric==2.8.0.post1\n", encoding="utf-8")
        assert locked_requirements(lock) == {
            "torch": "2.13.0",
            "torch-geometric": "2.8.0.post1",
        }
    print("training_runtime_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
