#!/usr/bin/env python3
"""Check required user-provided inputs for production readiness."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None
    return read_json(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def present(value: Any) -> bool:
    return isinstance(value, str) and value.strip() and not value.strip().upper().startswith("TBD")


def report_status(path: Path) -> str:
    report = read_json_or_none(path)
    if report is None:
        return "missing"
    return str(report.get("status", "unknown"))


def read_scope_policy(root: Path, rel_path: str) -> dict[str, Any]:
    policy = read_json_or_none(root / rel_path)
    return policy if isinstance(policy, dict) else {}


def required_check(
    name: str,
    ok: bool,
    source: str,
    needed_for: list[str],
    required: bool = True,
    observed_present: bool | None = None,
) -> dict[str, Any]:
    check = {
        "name": name,
        "ok": ok if required else True,
        "required": required,
        "waived": not required,
        "source": source,
        "needed_for": needed_for,
    }
    if observed_present is not None:
        check["observed_present"] = observed_present
    return check


def readiness_check(
    name: str,
    ok: bool,
    source: str,
    observed_status: str,
    needed_for: list[str],
    required: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok if required else True,
        "required": required,
        "waived": not required,
        "source": source,
        "observed_status": observed_status,
        "needed_for": needed_for,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check required external inputs.")
    parser.add_argument(
        "--contacts",
        default=os.environ.get("OPS_CONTACTS_CONFIG", "config/ops_contacts.local.json"),
    )
    parser.add_argument("--preflight-report", default="ops/reports/trace-endpoint-preflight.latest.json")
    parser.add_argument("--label-readiness-report", default="ops/reports/label-readiness-audit.latest.json")
    parser.add_argument("--handoff", default="ops/phase_b_handoff.md")
    parser.add_argument("--scope-policy", default="config/phase_b_scope.json")
    parser.add_argument("--out", default="ops/reports/required-inputs-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    scope_policy = read_scope_policy(root, args.scope_policy)
    trace_replay_required = scope_policy.get("trace_replay_required", True) is not False
    ops_contacts_required = scope_policy.get("ops_contacts_required", True) is not False
    contacts_path = root / args.contacts
    contacts = read_json(contacts_path) if contacts_path.exists() else {}
    eth_main_present = present(os.environ.get("ETH_MAIN_HTTP_URL"))
    user_input_checks = [
        required_check(
            "ETH_MAIN_HTTP_URL",
            eth_main_present,
            "environment",
            ["Geth/Erigon trace replay", "trace P95", "rich graph evidence"],
            required=trace_replay_required,
            observed_present=eth_main_present,
        ),
        required_check(
            "pager_or_feishu_target",
            present(contacts.get("pager_or_feishu_target")),
            args.contacts,
            ["gray launch readiness", "high/critical escalation"],
            required=ops_contacts_required,
        ),
        required_check(
            "phone_or_manual_escalation_target",
            present(contacts.get("phone_or_manual_escalation_target")),
            args.contacts,
            ["manual escalation path", "production go/no-go"],
            required=ops_contacts_required,
        ),
        required_check(
            "on_call_analyst",
            present(contacts.get("on_call_analyst")),
            args.contacts,
            ["operational handoff", "analyst review"],
            required=ops_contacts_required,
        ),
        required_check(
            "on_call_engineer",
            present(contacts.get("on_call_engineer")),
            args.contacts,
            ["trace/model/infra validation"],
            required=ops_contacts_required,
        ),
        required_check(
            "incident_commander",
            present(contacts.get("incident_commander")),
            args.contacts,
            ["critical incident coordination"],
            required=ops_contacts_required,
        ),
        required_check(
            "protocol_owner_or_partner_contact",
            present(contacts.get("protocol_owner_or_partner_contact")),
            args.contacts,
            ["protocol escalation", "partner notification"],
            required=ops_contacts_required,
        ),
        required_check(
            "multisig_signer_or_authorized_approver",
            present(contacts.get("multisig_signer_or_authorized_approver")),
            args.contacts,
            ["approval-gated suggested actions"],
            required=ops_contacts_required,
        ),
    ]
    preflight_path = root / args.preflight_report
    preflight_status = report_status(preflight_path)
    label_readiness_path = root / args.label_readiness_report
    label_readiness_status = report_status(label_readiness_path)
    handoff_path = root / args.handoff
    readiness_checks = [
        readiness_check(
            "trace_endpoint_preflight",
            preflight_status == "ok",
            args.preflight_report,
            preflight_status,
            ["real trace replay", "trace P95", "rich graph evidence"],
            required=trace_replay_required,
        ),
        readiness_check(
            "label_queue_trace_ready",
            label_readiness_status == "trace_ready",
            args.label_readiness_report,
            label_readiness_status,
            ["historical trace replay queue", "label promotion queue"],
            required=trace_replay_required,
        ),
        readiness_check(
            "phase_b_handoff_exists",
            handoff_path.exists(),
            args.handoff,
            "present" if handoff_path.exists() else "missing",
            ["operator handoff", "Phase B continuation"],
        ),
    ]
    missing_user_inputs = [
        check for check in user_input_checks if check.get("required", True) and not check["ok"]
    ]
    readiness_gaps = [
        check for check in readiness_checks if check.get("required", True) and not check["ok"]
    ]
    missing = missing_user_inputs + readiness_gaps
    if missing_user_inputs:
        status = "missing_inputs"
    elif readiness_gaps:
        status = "readiness_gaps"
    else:
        status = "ok"
    report = {
        "checked_at": now_iso(),
        "status": status,
        "contacts_config": args.contacts,
        "scope_policy": args.scope_policy,
        "scope_mode": scope_policy.get("mode", "default"),
        "trace_replay_required": trace_replay_required,
        "ops_contacts_required": ops_contacts_required,
        "preflight_report": args.preflight_report,
        "label_readiness_report": args.label_readiness_report,
        "handoff": args.handoff,
        "checks": user_input_checks + readiness_checks,
        "user_input_checks": user_input_checks,
        "readiness_checks": readiness_checks,
        "missing_user_inputs": missing_user_inputs,
        "readiness_gaps": readiness_gaps,
        "missing": missing,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
