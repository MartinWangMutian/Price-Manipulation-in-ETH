#!/usr/bin/env python3
"""Self-test for ops_contacts_bootstrap.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/ops_contacts_bootstrap.py"


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    (root / ".gitignore").write_text("config/ops_contacts.local.json\n", encoding="utf-8")


def run_bootstrap(root: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload == json.loads((root / "ops/reports/ops-contacts-bootstrap.latest.json").read_text(encoding="utf-8"))
    return payload  # type: ignore[return-value]


def test_creates_ignored_local_contacts() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        init_repo(root)
        (root / "config").mkdir()
        (root / "config/ops_contacts.example.json").write_text('{"schema_ver": "ops-contacts.v1"}\n', encoding="utf-8")
        report = run_bootstrap(root)
        assert report["status"] == "created"
        assert report["created"] is True
        assert report["git_ignored"] is True
        assert (root / "config/ops_contacts.local.json").exists()


def test_does_not_overwrite_existing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        init_repo(root)
        (root / "config").mkdir()
        (root / "config/ops_contacts.example.json").write_text('{"schema_ver": "ops-contacts.v1"}\n', encoding="utf-8")
        (root / "config/ops_contacts.local.json").write_text('{"custom": true}\n', encoding="utf-8")
        report = run_bootstrap(root)
        assert report["status"] == "exists"
        assert report["created"] is False
        assert json.loads((root / "config/ops_contacts.local.json").read_text(encoding="utf-8")) == {"custom": True}


def main() -> int:
    test_creates_ignored_local_contacts()
    test_does_not_overwrite_existing()
    print(json.dumps({"status": "ok", "tests": 2}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
