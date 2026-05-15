#!/usr/bin/env python3
"""Self-test for report_secret_audit.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/report_secret_audit.py"


def run_audit(root: Path, expect_ok: bool) -> dict[str, object]:
    out = "ops/reports/report-secret-audit.latest.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", "ops/reports", "--out", out],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) is expect_ok, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload == json.loads((root / out).read_text(encoding="utf-8"))
    return payload  # type: ignore[return-value]


def test_clean_report() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        report_dir = root / "ops/reports"
        report_dir.mkdir(parents=True)
        (report_dir / "env-local-audit.latest.json").write_text(
            json.dumps({"host": "eth-mainnet.g.alchemy.com", "path_redacted": True}),
            encoding="utf-8",
        )
        report = run_audit(root, expect_ok=True)
        assert report["status"] == "ok"
        assert report["findings"] == []


def test_leaked_alchemy_path() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        report_dir = root / "ops/reports"
        report_dir.mkdir(parents=True)
        (report_dir / "bad.json").write_text(
            json.dumps({"url": "https://eth-mainnet.g.alchemy.com/v2/secret"}),
            encoding="utf-8",
        )
        report = run_audit(root, expect_ok=False)
        assert report["status"] == "failed"
        assert report["findings"][0]["pattern"] == "alchemy_v2_url_path"


def main() -> int:
    test_clean_report()
    test_leaked_alchemy_path()
    print(json.dumps({"status": "ok", "tests": 2}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
