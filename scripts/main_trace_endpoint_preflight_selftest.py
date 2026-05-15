#!/usr/bin/env python3
"""Self-test for main_trace_endpoint_preflight.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/main_trace_endpoint_preflight.py"


def run_dry(root: Path) -> dict[str, object]:
    out = "ops/reports/trace-endpoint-preflight.plan.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", ".env.local", "--dry-run", "--out", out],
        cwd=root,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload == json.loads((root / out).read_text(encoding="utf-8"))
    return payload  # type: ignore[return-value]


def run_dry_with_env(root: Path, env: dict[str, str]) -> dict[str, object]:
    out = "ops/reports/trace-endpoint-preflight.plan.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", ".env.local", "--dry-run", "--out", out],
        cwd=root,
        env={**os.environ, **env},
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload == json.loads((root / out).read_text(encoding="utf-8"))
    return payload  # type: ignore[return-value]


def test_ready_to_preflight() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text(
            'export ETH_MAIN_HTTP_URL="https://trace-mainnet.example.com/v2/secret"\n',
            encoding="utf-8",
        )
        report = run_dry(root)
        assert report["status"] == "ready_to_preflight"
        assert report["main_trace_http_check"]["host"] == "trace-mainnet.example.com"
        assert "v2/secret" not in json.dumps(report)


def test_invalid_main_trace_url() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text(
            'export ETH_MAIN_HTTP_URL="wss://trace-mainnet.example.com/v2/secret"\n',
            encoding="utf-8",
        )
        report = run_dry(root)
        assert report["status"] == "missing_or_invalid_main_trace_http_url"
        assert report["main_trace_http_check"]["error"] == "invalid_url_or_scheme"


def test_environment_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text("", encoding="utf-8")
        report = run_dry_with_env(root, {"ETH_MAIN_HTTP_URL": "https://trace-mainnet.example.com/v2/secret"})
        assert report["status"] == "ready_to_preflight"
        assert report["main_trace_http_source"] == "environment"
        assert report["main_trace_http_check"]["host"] == "trace-mainnet.example.com"


def main() -> int:
    test_ready_to_preflight()
    test_invalid_main_trace_url()
    test_environment_fallback()
    print(json.dumps({"status": "ok", "tests": 3}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
