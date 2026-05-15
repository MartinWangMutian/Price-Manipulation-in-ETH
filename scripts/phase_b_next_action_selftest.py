#!/usr/bin/env python3
"""Self-test for phase_b_next_action.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/phase_b_next_action.py"


def write_json(root: Path, rel_path: str, payload: object) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_next(root: Path) -> dict[str, object]:
    out = "ops/reports/phase-b-next-action.latest.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", out],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload == json.loads((root / out).read_text(encoding="utf-8"))
    return payload  # type: ignore[return-value]


def seed_blocked(root: Path) -> None:
    write_json(root, "ops/reports/env-local-audit.latest.json", {"status": "provider_configured_main_missing", "provider_ready": True, "main_trace_ready": False})
    write_json(
        root,
        "ops/reports/required-inputs-check.latest.json",
        {"status": "missing_inputs", "missing_user_inputs": [{"name": "ETH_MAIN_HTTP_URL"}]},
    )
    write_json(root, "ops/reports/phase-b-completion-audit.latest.json", {"status": "blocked_user_input"})
    write_json(root, "ops/reports/trace-endpoint-preflight.latest.json", {"status": "missing_endpoint"})
    write_json(root, "ops/reports/historical-trace-results-audit.latest.json", {"status": "awaiting_real_replay"})


def test_run_provider_trace_probe() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        seed_blocked(root)
        report = run_next(root)
        assert report["selected_action"]["action_id"] == "run_provider_trace_probe"
        assert any("phase_b_refresh.py" in command for command in report["selected_action"]["commands"])


def test_promote_provider_to_main_trace_env() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        seed_blocked(root)
        write_json(root, "ops/reports/provider-trace-capability-probe.latest.json", {"status": "ok", "selected_method": "debug_traceTransaction"})
        report = run_next(root)
        assert report["selected_action"]["action_id"] == "promote_provider_to_main_trace_env"
        assert any("phase_b_refresh.py" in command for command in report["selected_action"]["commands"])


def test_apply_for_trace_endpoint() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        seed_blocked(root)
        write_json(
            root,
            "ops/reports/provider-trace-capability-probe.latest.json",
            {
                "status": "degraded",
                "checks": [
                    {"name": "eth_chainId", "ok": True},
                    {"name": "debug_traceTransaction", "ok": False, "error": {"code": -32600}},
                ],
            },
        )
        report = run_next(root)
        assert report["selected_action"]["action_id"] == "apply_for_trace_endpoint"
        assert report["selected_action"]["evidence"]["failed_trace_methods"][0]["name"] == "debug_traceTransaction"
        assert report["selected_action"]["next_steps"]


def main() -> int:
    test_run_provider_trace_probe()
    test_promote_provider_to_main_trace_env()
    test_apply_for_trace_endpoint()
    print(json.dumps({"status": "ok", "tests": 3}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
