#!/usr/bin/env python3
"""Select the next concrete Phase B action from local reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def status(report: Any | None) -> str:
    if report is None:
        return "missing"
    return str(report.get("status", "unknown"))


def command_action(action_id: str, owner: str, reason: str, command: list[str]) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "owner": owner,
        "reason": reason,
        "commands": command,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pick the next concrete Phase B action.")
    parser.add_argument("--out", default="ops/reports/phase-b-next-action.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    env_local = read_json_or_none(root / "ops/reports/env-local-audit.latest.json")
    provider_probe = read_json_or_none(root / "ops/reports/provider-trace-capability-probe.latest.json")
    required = read_json_or_none(root / "ops/reports/required-inputs-check.latest.json")
    phase_b = read_json_or_none(root / "ops/reports/phase-b-completion-audit.latest.json")
    trace_preflight = read_json_or_none(root / "ops/reports/trace-endpoint-preflight.latest.json")
    trace_results = read_json_or_none(root / "ops/reports/historical-trace-results-audit.latest.json")

    missing_user_inputs = required.get("missing_user_inputs", []) if required else []
    missing_names = {item.get("name") for item in missing_user_inputs}
    provider_ready = bool(env_local and env_local.get("provider_ready"))
    main_trace_ready = bool(env_local and env_local.get("main_trace_ready"))

    if status(phase_b) == "complete":
        action = {
            "action_id": "none_phase_b_complete",
            "owner": "none",
            "reason": "Phase B completion audit is complete.",
            "commands": [],
        }
    elif status(provider_probe) == "ok" and provider_probe.get("selected_method") and "ETH_MAIN_HTTP_URL" in missing_names:
        action = command_action(
            "promote_provider_to_main_trace_env",
            "user",
            "Provider trace probe passed; configure ETH_MAIN_HTTP_URL before standard preflight.",
            [
                'export ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"',
                "python3 scripts/trace_endpoint_preflight.py "
                "--queue data/training/trace_replay_queue.v1.json "
                "--method auto "
                "--out ops/reports/trace-endpoint-preflight.latest.json",
            ],
        )
    elif provider_ready and status(provider_probe) == "missing" and not main_trace_ready:
        action = command_action(
            "run_provider_trace_probe",
            "user",
            "Provider HTTP URL is configured and dry-run is ready, but real provider trace probe has not run.",
            [
                "python3 scripts/provider_trace_capability_probe.py "
                "--env-file .env.local "
                "--queue data/training/trace_replay_queue.v1.json "
                "--method auto "
                "--out ops/reports/provider-trace-capability-probe.latest.json",
                "python3 scripts/report_secret_audit.py "
                "--input ops/reports "
                "--out ops/reports/report-secret-audit.latest.json",
            ],
        )
    elif status(provider_probe) == "degraded" and "ETH_MAIN_HTTP_URL" in missing_names:
        action = {
            "action_id": "apply_for_trace_endpoint",
            "owner": "user",
            "reason": "Provider RPC is not sufficient for historical trace replay.",
            "commands": [],
            "needed": "Ethereum mainnet Geth/Erigon HTTP endpoint supporting debug_traceTransaction or trace_transaction",
        }
    elif main_trace_ready and status(trace_preflight) != "ok":
        action = command_action(
            "run_trace_endpoint_preflight",
            "user",
            "ETH_MAIN_HTTP_URL appears configured but standard trace endpoint preflight has not passed.",
            [
                "source .env.local",
                "python3 scripts/trace_endpoint_preflight.py "
                "--queue data/training/trace_replay_queue.v1.json "
                "--method auto "
                "--out ops/reports/trace-endpoint-preflight.latest.json",
            ],
        )
    elif status(trace_preflight) == "ok" and status(trace_results) != "ok":
        action = command_action(
            "run_historical_trace_replay",
            "project",
            "Trace endpoint preflight passed; replay exploit and normal trace queues.",
            [
                "python3 scripts/historical_trace_replay.py "
                "--queue data/training/trace_replay_queue.v1.json "
                "--method auto "
                "--out ops/reports/historical-trace-replay.latest.json",
                "python3 scripts/historical_trace_replay.py "
                "--queue data/training/normal_trace_replay_queue.v1.json "
                "--method auto "
                "--out ops/reports/normal-historical-trace-replay.latest.json",
                "python3 scripts/historical_trace_results_audit.py "
                "--out ops/reports/historical-trace-results-audit.latest.json",
            ],
        )
    elif missing_names:
        action = {
            "action_id": "fill_required_user_inputs",
            "owner": "user",
            "reason": "Required user inputs are still missing.",
            "commands": [],
            "missing_user_inputs": sorted(str(name) for name in missing_names if name),
        }
    else:
        action = command_action(
            "refresh_phase_b_audits",
            "project",
            "No more specific action was selected; refresh Phase B gates.",
            [
                "python3 scripts/required_inputs_check.py "
                "--contacts \"${OPS_CONTACTS_CONFIG:-config/ops_contacts.example.json}\" "
                "--out ops/reports/required-inputs-check.latest.json",
                "python3 scripts/phase_b_completion_audit.py "
                "--out ops/reports/phase-b-completion-audit.latest.json",
                "python3 scripts/status_summary.py --out ops/status_summary.md",
            ],
        )

    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "selected_action": action,
        "inputs": {
            "env_local_status": status(env_local),
            "provider_probe_status": status(provider_probe),
            "required_inputs_status": status(required),
            "phase_b_completion_status": status(phase_b),
            "trace_preflight_status": status(trace_preflight),
            "trace_results_status": status(trace_results),
        },
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
