#!/usr/bin/env python3
"""Self-test for provider_trace_capability_probe.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/provider_trace_capability_probe.py"


def run_dry(root: Path) -> dict[str, object]:
    out = "ops/reports/provider-trace-capability-probe.plan.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env-file", ".env.local", "--dry-run", "--out", out],
        cwd=root,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload == json.loads((root / out).read_text(encoding="utf-8"))
    return payload  # type: ignore[return-value]


def test_ready_to_probe() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text(
            'export ETH_PROVIDER_HTTP_URL="https://eth-mainnet.g.alchemy.com/v2/secret"\n',
            encoding="utf-8",
        )
        report = run_dry(root)
        assert report["status"] == "ready_to_probe"
        assert report["provider_http_check"]["host"] == "eth-mainnet.g.alchemy.com"
        assert "v2/secret" not in json.dumps(report)


def test_invalid_provider_url() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".env.local").write_text(
            'export ETH_PROVIDER_HTTP_URL="https:https://eth-mainnet.g.alchemy.com/v2/secret"\n',
            encoding="utf-8",
        )
        report = run_dry(root)
        assert report["status"] == "missing_or_invalid_provider_http_url"
        assert report["provider_http_check"]["error"] == "invalid_url_or_scheme"


def main() -> int:
    test_ready_to_probe()
    test_invalid_provider_url()
    print(json.dumps({"status": "ok", "tests": 2}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
