#!/usr/bin/env python3
"""Self-test for env_local_audit.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/env_local_audit.py"


def run_audit(root: Path) -> dict[str, object]:
    out = "ops/reports/env-local-audit.latest.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", ".env.local", "--out", out],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads((root / out).read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    return file_payload  # type: ignore[return-value]


def test_provider_configured_main_missing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text(
            "\n".join(
                [
                    'export ETH_PROVIDER_HTTP_URL="https://eth-mainnet.g.alchemy.com/v2/secret"',
                    'export ETH_PROVIDER_WS_URL="wss://eth-mainnet.g.alchemy.com/v2/secret"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        report = run_audit(root)
        assert report["status"] == "provider_configured_main_missing"
        assert report["provider_ready"] is True
        assert report["main_trace_ready"] is False
        provider_http = next(check for check in report["checks"] if check["name"] == "ETH_PROVIDER_HTTP_URL")
        assert provider_http["host"] == "eth-mainnet.g.alchemy.com"
        assert "v2/secret" not in json.dumps(report)


def test_malformed_url() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text(
            'export ETH_PROVIDER_HTTP_URL="https:https://eth-mainnet.g.alchemy.com/v2/secret"\n',
            encoding="utf-8",
        )
        report = run_audit(root)
        provider_http = next(check for check in report["checks"] if check["name"] == "ETH_PROVIDER_HTTP_URL")
        assert provider_http["ok"] is False
        assert provider_http["error"] == "invalid_url_or_scheme"


def test_main_trace_configured() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text(
            "\n".join(
                [
                    'export ETH_PROVIDER_HTTP_URL="https://eth-mainnet.g.alchemy.com/v2/secret"',
                    'export ETH_PROVIDER_WS_URL="wss://eth-mainnet.g.alchemy.com/v2/secret"',
                    'export ETH_MAIN_HTTP_URL="https://trace.example.invalid/rpc/secret"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        report = run_audit(root)
        assert report["status"] == "main_trace_env_configured"
        assert report["main_trace_ready"] is True


def main() -> int:
    test_provider_configured_main_missing()
    test_malformed_url()
    test_main_trace_configured()
    print(json.dumps({"status": "ok", "tests": 3}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
