#!/usr/bin/env python3
"""Synthetic checks for training_run_guard.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import training_run_guard as guard


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "data"
        target.mkdir()
        (target / "a.json").write_text("{}\n", encoding="utf-8")
        first = guard.snapshot_path(root, target)
        second = guard.snapshot_path(root, target)
        assert first == second, (first, second)
        assert first["files"] == 1, first
        assert first["bytes"] == 3, first
        (target / "a.json").write_text('{"x":1}\n', encoding="utf-8")
        changed = guard.snapshot_path(root, target)
        assert changed["sha256"] != first["sha256"], (first, changed)
        missing = guard.snapshot_path(root, root / "missing")
        assert missing["exists"] is False, missing
        env_file = root / ".env.local"
        env_file.write_text('export ETH_PROVIDER_HTTP_URL="https://example.invalid/key"\n', encoding="utf-8")
        environment = guard.environment_policy(env_file)
        assert environment["ready"] is True, environment
        assert environment["runtime_mapping"] == "ETH_MAIN_HTTP_URL<-ETH_PROVIDER_HTTP_URL", environment
        assert "example.invalid" not in str(environment), environment
    print("training_run_guard_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
