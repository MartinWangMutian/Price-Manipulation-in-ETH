#!/usr/bin/env python3
"""Self-test for phase_b_completion_audit.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/phase_b_completion_audit.py"


def write_json(root: Path, rel_path: str, payload: object) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def run_audit(root: Path) -> dict[str, object]:
    out = "ops/reports/phase-b-completion-audit.latest.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", out],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    stdout_payload = json.loads(result.stdout)
    file_payload = read_json(root / out)
    assert stdout_payload == file_payload
    return file_payload  # type: ignore[return-value]


def seed_common(root: Path) -> None:
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "ops/phase_b_handoff.md").write_text("# handoff\n", encoding="utf-8")
    (root / "ops/post_endpoint_trace_runbook.md").write_text("# runbook\n", encoding="utf-8")
    write_json(root, "ops/reports/project-status.latest.json", {"provider_only_shadow_pipeline": "ok"})
    write_json(
        root,
        "ops/reports/label-readiness-audit.latest.json",
        {"status": "trace_ready", "total_trace_queue_items": 57},
    )
    write_json(
        root,
        "ops/reports/label-promotion-audit.latest.json",
        {"status": "ok", "decision_counts": {"pending_trace": 57}, "promoted_markers": 0},
    )
    write_json(root, "ops/reports/training-dataset-check.latest.json", {"status": "ok", "training_ready": False})


def test_blocked_user_input() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        seed_common(root)
        write_json(
            root,
            "ops/reports/required-inputs-check.latest.json",
            {
                "status": "missing_inputs",
                "missing_user_inputs": [
                    {"name": "ETH_MAIN_HTTP_URL"},
                    {"name": "pager_or_feishu_target"},
                ],
                "readiness_gaps": [{"name": "trace_endpoint_preflight"}],
            },
        )
        write_json(
            root,
            "ops/reports/trace-endpoint-preflight.latest.json",
            {"status": "missing_endpoint", "endpoint_configured": False, "selected_method": None},
        )
        write_json(
            root,
            "ops/reports/historical-trace-results-audit.latest.json",
            {"status": "awaiting_real_replay", "written_total": 0, "expected_total": 57},
        )
        report = run_audit(root)
        assert report["status"] == "blocked_user_input"
        assert report["phase_b_complete"] is False
        assert "trace_endpoint_preflight_ok" in report["user_blockers"]
        contact_check = next(check for check in report["checks"] if check["name"] == "ops_contacts_configured")
        assert contact_check["evidence"]["missing_contact_inputs"] == ["pager_or_feishu_target"]


def test_complete() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        seed_common(root)
        write_json(
            root,
            "ops/reports/required-inputs-check.latest.json",
            {"status": "ok", "missing_user_inputs": [], "readiness_gaps": []},
        )
        write_json(
            root,
            "ops/reports/trace-endpoint-preflight.latest.json",
            {"status": "ok", "endpoint_configured": True, "selected_method": "debug_traceTransaction"},
        )
        write_json(
            root,
            "ops/reports/historical-trace-results-audit.latest.json",
            {"status": "ok", "written_total": 57, "expected_total": 57},
        )
        write_json(
            root,
            "ops/reports/label-promotion-audit.latest.json",
            {"status": "ok", "decision_counts": {"pending_trace": 0}, "promoted_markers": 57},
        )
        write_json(root, "ops/reports/training-dataset-check.latest.json", {"status": "ok", "training_ready": True})
        report = run_audit(root)
        assert report["status"] == "complete"
        assert report["phase_b_complete"] is True
        assert report["missing_checks"] == []


def main() -> int:
    test_blocked_user_input()
    test_complete()
    print(json.dumps({"status": "ok", "tests": 2}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
