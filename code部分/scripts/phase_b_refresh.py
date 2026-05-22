#!/usr/bin/env python3
"""Refresh local Phase B readiness reports without network trace probes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def run_step(root: Path, name: str, command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    return {
        "name": name,
        "command": command,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh local Phase B readiness reports. This does not call live trace endpoints."
    )
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--contacts", default=os.environ.get("OPS_CONTACTS_CONFIG", "config/ops_contacts.local.json"))
    parser.add_argument("--out", default="ops/reports/phase-b-refresh.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    py = sys.executable
    steps = [
        (
            "ops_contacts_bootstrap",
            [
                py,
                "scripts/ops_contacts_bootstrap.py",
                "--report",
                "ops/reports/ops-contacts-bootstrap.latest.json",
            ],
        ),
        (
            "env_local_audit",
            [
                py,
                "scripts/env_local_audit.py",
                "--env-file",
                args.env_file,
                "--out",
                "ops/reports/env-local-audit.latest.json",
            ],
        ),
        (
            "required_inputs_check",
            [
                py,
                "scripts/required_inputs_check.py",
                "--contacts",
                args.contacts,
                "--out",
                "ops/reports/required-inputs-check.latest.json",
            ],
        ),
        (
            "phase_b_completion_audit",
            [
                py,
                "scripts/phase_b_completion_audit.py",
                "--out",
                "ops/reports/phase-b-completion-audit.latest.json",
            ],
        ),
        (
            "phase_b_next_action",
            [
                py,
                "scripts/phase_b_next_action.py",
                "--out",
                "ops/reports/phase-b-next-action.latest.json",
            ],
        ),
        (
            "artifact_manifest",
            [
                py,
                "scripts/artifact_manifest.py",
                "--out",
                "ops/reports/artifact-manifest.latest.json",
            ],
        ),
        (
            "status_summary",
            [
                py,
                "scripts/status_summary.py",
                "--out",
                "ops/status_summary.md",
            ],
        ),
        (
            "report_secret_audit",
            [
                py,
                "scripts/report_secret_audit.py",
                "--input",
                "ops/reports",
                "--out",
                "ops/reports/report-secret-audit.latest.json",
            ],
        ),
    ]

    results = [run_step(root, name, command) for name, command in steps]
    failed = [step["name"] for step in results if not step["ok"]]
    report = {
        "checked_at": now_iso(),
        "status": "failed" if failed else "ok",
        "env_file": args.env_file,
        "contacts": args.contacts,
        "network_trace_probe": "not_run",
        "failed_steps": failed,
        "steps": results,
        "next_action_report": "ops/reports/phase-b-next-action.latest.json",
        "status_summary": "ops/status_summary.md",
    }
    write_json(root / args.out, report)
    print(json.dumps({k: v for k, v in report.items() if k != "steps"}, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
