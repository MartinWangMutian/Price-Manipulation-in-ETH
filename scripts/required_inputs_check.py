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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def present(value: Any) -> bool:
    return isinstance(value, str) and value.strip() and not value.strip().upper().startswith("TBD")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check required external inputs.")
    parser.add_argument(
        "--contacts",
        default=os.environ.get("OPS_CONTACTS_CONFIG", "config/ops_contacts.example.json"),
    )
    parser.add_argument("--out", default="ops/reports/required-inputs-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    contacts_path = root / args.contacts
    contacts = read_json(contacts_path) if contacts_path.exists() else {}
    checks = [
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
            "name": "multisig_signer_or_authorized_approver",
            "ok": present(contacts.get("multisig_signer_or_authorized_approver")),
            "source": args.contacts,
            "needed_for": ["approval-gated suggested actions"],
        },
    ]
    missing = [check for check in checks if not check["ok"]]
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not missing else "missing_inputs",
        "contacts_config": args.contacts,
        "checks": checks,
        "missing": missing,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
