#!/usr/bin/env python3
"""Self-test for artifact_manifest.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/artifact_manifest.py"


def test_excludes_local_contacts() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "config").mkdir(parents=True)
        (root / "config/ops_contacts.example.json").write_text("{}", encoding="utf-8")
        (root / "config/ops_contacts.local.json").write_text('{"secret": "local"}', encoding="utf-8")
        out = "ops/reports/artifact-manifest.latest.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--out", out],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        file_payload = json.loads((root / out).read_text(encoding="utf-8"))
        assert payload["counts"] == file_payload["counts"]
        assert "config/ops_contacts.example.json" in file_payload["categories"]["config"]
        assert "config/ops_contacts.local.json" not in file_payload["categories"]["config"]
        assert "config/ops_contacts.local.json" in file_payload["excluded_artifacts"]


def main() -> int:
    test_excludes_local_contacts()
    print(json.dumps({"status": "ok", "tests": 1}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
