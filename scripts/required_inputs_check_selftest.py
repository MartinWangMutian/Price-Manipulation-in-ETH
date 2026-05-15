#!/usr/bin/env python3
"""Self-test for required_inputs_check.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/required_inputs_check.py"


CONTACTS = {
    "schema_ver": "ops-contacts.v1",
    "pager_or_feishu_target": "feishu://security-alerts",
    "phone_or_manual_escalation_target": "+1-555-0100",
    "on_call_analyst": "analyst-a",
    "on_call_engineer": "engineer-a",
    "incident_commander": "commander-a",
    "protocol_owner_or_partner_contact": "partner-a",
    "multisig_signer_or_authorized_approver": "approver-a",
}


def write_json(root: Path, rel_path: str, payload: object) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_check(root: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    out = "ops/reports/required-inputs-check.latest.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contacts",
            "config/ops_contacts.local.json",
            "--out",
            out,
        ],
        cwd=root,
        env={**os.environ, **(env or {})},
        check=True,
        text=True,
        capture_output=True,
    )
    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads((root / out).read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    return file_payload  # type: ignore[return-value]


def seed_ready_reports(root: Path) -> None:
    write_json(root, "ops/reports/trace-endpoint-preflight.latest.json", {"status": "ok"})
    write_json(root, "ops/reports/label-readiness-audit.latest.json", {"status": "trace_ready"})
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "ops/phase_b_handoff.md").write_text("# handoff\n", encoding="utf-8")


def test_ok() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        write_json(root, "config/ops_contacts.local.json", CONTACTS)
        seed_ready_reports(root)
        report = run_check(root, {"ETH_MAIN_HTTP_URL": "http://127.0.0.1:8545"})
        assert report["status"] == "ok"
        assert report["missing_user_inputs"] == []
        assert report["readiness_gaps"] == []


def test_missing_contacts_and_readiness_gap() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        incomplete_contacts = {**CONTACTS, "protocol_owner_or_partner_contact": "TBD"}
        write_json(root, "config/ops_contacts.local.json", incomplete_contacts)
        write_json(root, "ops/reports/trace-endpoint-preflight.latest.json", {"status": "missing_endpoint"})
        write_json(root, "ops/reports/label-readiness-audit.latest.json", {"status": "trace_ready"})
        (root / "ops/phase_b_handoff.md").write_text("# handoff\n", encoding="utf-8")
        report = run_check(root, {})
        missing_user_names = [item["name"] for item in report["missing_user_inputs"]]
        readiness_gap_names = [item["name"] for item in report["readiness_gaps"]]
        assert report["status"] == "missing_inputs"
        assert "ETH_MAIN_HTTP_URL" in missing_user_names
        assert "protocol_owner_or_partner_contact" in missing_user_names
        assert readiness_gap_names == ["trace_endpoint_preflight"]


def test_readiness_only_gap() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        write_json(root, "config/ops_contacts.local.json", CONTACTS)
        write_json(root, "ops/reports/trace-endpoint-preflight.latest.json", {"status": "degraded"})
        write_json(root, "ops/reports/label-readiness-audit.latest.json", {"status": "trace_ready"})
        (root / "ops/phase_b_handoff.md").write_text("# handoff\n", encoding="utf-8")
        report = run_check(root, {"ETH_MAIN_HTTP_URL": "http://127.0.0.1:8545"})
        assert report["status"] == "readiness_gaps"
        assert report["missing_user_inputs"] == []
        assert [item["name"] for item in report["readiness_gaps"]] == ["trace_endpoint_preflight"]


def test_course_no_trace_waives_trace_and_contacts() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        write_json(
            root,
            "config/phase_b_scope.json",
            {
                "mode": "course_no_trace",
                "trace_replay_required": False,
                "ops_contacts_required": False,
            },
        )
        write_json(root, "ops/reports/trace-endpoint-preflight.latest.json", {"status": "degraded"})
        write_json(root, "ops/reports/label-readiness-audit.latest.json", {"status": "missing"})
        (root / "ops").mkdir(parents=True, exist_ok=True)
        (root / "ops/phase_b_handoff.md").write_text("# handoff\n", encoding="utf-8")
        report = run_check(root, {})
        assert report["status"] == "ok"
        assert report["trace_replay_required"] is False
        assert report["ops_contacts_required"] is False
        assert report["missing_user_inputs"] == []
        assert report["readiness_gaps"] == []
        waived = {item["name"] for item in report["checks"] if item.get("waived")}
        assert "ETH_MAIN_HTTP_URL" in waived
        assert "trace_endpoint_preflight" in waived


def main() -> int:
    test_ok()
    test_missing_contacts_and_readiness_gap()
    test_readiness_only_gap()
    test_course_no_trace_waives_trace_and_contacts()
    print(json.dumps({"status": "ok", "tests": 4}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
