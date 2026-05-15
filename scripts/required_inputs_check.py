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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check required external inputs.")
    parser.add_argument(
        "--contacts",
        default=os.environ.get("OPS_CONTACTS_CONFIG", "config/ops_contacts.example.json"),
    )
    parser.add_argument("--preflight-report", default="ops/reports/trace-endpoint-preflight.latest.json")
    parser.add_argument("--label-readiness-report", default="ops/reports/label-readiness-audit.latest.json")
    parser.add_argument("--handoff", default="ops/phase_b_handoff.md")
    parser.add_argument("--out", default="ops/reports/required-inputs-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    contacts_path = root / args.contacts
    contacts = read_json(contacts_path) if contacts_path.exists() else {}
    user_input_checks = [
        {
            "name": "ETH_MAIN_HTTP_URL",
            "ok": present(os.environ.get("ETH_MAIN_HTTP_URL")),
            "source": "environment",
            "needed_for": ["Geth/Erigon trace replay", "trace P95", "rich graph evidence"],
        },
        {
            "name": "pager_or_feishu_target",
            "ok": present(contacts.get("pager_or_feishu_target")),
            "source": args.contacts,
            "needed_for": ["gray launch readiness", "high/critical escalation"],
        },
        {
            "name": "phone_or_manual_escalation_target",
            "ok": present(contacts.get("phone_or_manual_escalation_target")),
            "source": args.contacts,
            "needed_for": ["manual escalation path", "production go/no-go"],
        },
        {
            "name": "on_call_analyst",
            "ok": present(contacts.get("on_call_analyst")),
            "source": args.contacts,
            "needed_for": ["operational handoff", "analyst review"],
        },
        {
            "name": "on_call_engineer",
            "ok": present(contacts.get("on_call_engineer")),
            "source": args.contacts,
            "needed_for": ["trace/model/infra validation"],
        },
        {
            "name": "incident_commander",
            "ok": present(contacts.get("incident_commander")),
            "source": args.contacts,
            "needed_for": ["critical incident coordination"],
        },
        {
            "name": "protocol_owner_or_partner_contact",
            "ok": present(contacts.get("protocol_owner_or_partner_contact")),
            "source": args.contacts,
            "needed_for": ["protocol escalation", "partner notification"],
        },
        {
            "name": "multisig_signer_or_authorized_approver",
            "ok": present(contacts.get("multisig_signer_or_authorized_approver")),
            "source": args.contacts,
            "needed_for": ["approval-gated suggested actions"],
        },
    ]
    preflight_path = root / args.preflight_report
    preflight_status = report_status(preflight_path)
    label_readiness_path = root / args.label_readiness_report
    label_readiness_status = report_status(label_readiness_path)
    handoff_path = root / args.handoff
    readiness_checks = [
        {
            "name": "trace_endpoint_preflight",
            "ok": preflight_status == "ok",
            "source": args.preflight_report,
            "observed_status": preflight_status,
            "needed_for": ["real trace replay", "trace P95", "rich graph evidence"],
        },
        {
            "name": "label_queue_trace_ready",
            "ok": label_readiness_status == "trace_ready",
            "source": args.label_readiness_report,
            "observed_status": label_readiness_status,
            "needed_for": ["historical trace replay queue", "label promotion queue"],
        },
        {
            "name": "phase_b_handoff_exists",
            "ok": handoff_path.exists(),
            "source": args.handoff,
            "needed_for": ["operator handoff", "Phase B continuation"],
        },
    ]
    missing_user_inputs = [check for check in user_input_checks if not check["ok"]]
    readiness_gaps = [check for check in readiness_checks if not check["ok"]]
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
