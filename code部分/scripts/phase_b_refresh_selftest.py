#!/usr/bin/env python3
"""Self-test for phase_b_refresh.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/phase_b_refresh.py"


def copy_script(root: Path, rel_path: str) -> None:
    source = REPO_ROOT / rel_path
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def write_json(root: Path, rel_path: str, payload: object) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def seed_minimal_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
    (root / ".gitignore").write_text("config/ops_contacts.local.json\n", encoding="utf-8")
    for rel_path in [
        "scripts/ops_contacts_bootstrap.py",
        "scripts/env_local_audit.py",
        "scripts/required_inputs_check.py",
        "scripts/phase_b_completion_audit.py",
        "scripts/phase_b_next_action.py",
        "scripts/artifact_manifest.py",
        "scripts/status_summary.py",
        "scripts/report_secret_audit.py",
    ]:
        copy_script(root, rel_path)
    write_json(root, "config/ops_contacts.example.json", {"schema_ver": "ops-contacts.v1"})
    write_json(root, "ops/reports/project-status.latest.json", {"status": "ok", "provider_only_shadow_pipeline": "ok"})
    write_json(root, "ops/reports/go-no-go-audit.latest.json", {"status": "no_go"})
    write_json(root, "ops/reports/validation-metrics-audit.latest.json", {"status": "not_pass"})
    write_json(root, "ops/reports/provider-trace-capability-probe.plan.json", {"status": "ready_to_probe"})
    write_json(root, "ops/reports/label-readiness-audit.latest.json", {"status": "trace_ready", "total_trace_queue_items": 0})
    write_json(root, "ops/reports/trace-endpoint-preflight.latest.json", {"status": "missing_endpoint"})
    write_json(root, "ops/reports/historical-trace-results-audit.latest.json", {"status": "awaiting_real_replay"})
    write_json(root, "ops/reports/historical-trace-replay.latest.json", {"status": "dry_run_ok"})
    write_json(root, "ops/reports/normal-historical-trace-replay.latest.json", {"status": "dry_run_ok"})
    write_json(root, "ops/reports/label-promotion-audit.latest.json", {"status": "ok", "decision_counts": {}, "promoted_markers": 0})
    write_json(root, "ops/reports/training-dataset-check.latest.json", {"status": "ok", "training_ready": False})
    (root / "ops/phase_b_handoff.md").write_text("# handoff\n", encoding="utf-8")


def test_refresh_runs_without_network_probe() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        seed_minimal_repo(root)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--out", "ops/reports/phase-b-refresh.latest.json"],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )
        stdout_payload = json.loads(result.stdout)
        report = json.loads((root / "ops/reports/phase-b-refresh.latest.json").read_text(encoding="utf-8"))
        assert stdout_payload["status"] == "ok"
        assert report["network_trace_probe"] == "not_run"
        step_names = [step["name"] for step in report["steps"]]
        assert "phase_b_next_action" in step_names
        assert "provider_trace_capability_probe" not in step_names
        assert (root / "ops/status_summary.md").exists()


def main() -> int:
    test_refresh_runs_without_network_probe()
    print(json.dumps({"status": "ok", "tests": 1}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
