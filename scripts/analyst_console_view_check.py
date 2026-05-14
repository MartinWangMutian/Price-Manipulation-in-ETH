#!/usr/bin/env python3
"""Validate analyst console view-model outputs."""

from __future__ import annotations

import argparse
import json
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


def audit_log_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate analyst console view-models.")
    parser.add_argument("--console-dir", default="data/console")
    parser.add_argument("--state-machine", default="config/review_state_machine.json")
    parser.add_argument("--out", default="ops/reports/analyst-console-view-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    console_dir = root / args.console_dir
    state_machine = read_json(root / args.state_machine)
    allowed_states = set(state_machine["states"])
    list_path = console_dir / "alerts-list.v1.json"
    detail_dir = console_dir / "alerts-detail.v1"
    audit_path = console_dir / "review-audit-trail.v1.jsonl"
    errors: list[str] = []
    alert_list = read_json(list_path)
    alerts = alert_list.get("alerts", [])
    detail_files = sorted(detail_dir.glob("*.json"))
    if len(alerts) != len(detail_files):
        errors.append("alert list and detail count mismatch")
    for item in alerts:
        if item.get("review_state") not in allowed_states:
            errors.append(f"invalid review state {item.get('review_state')}")
            break
    required_detail_sections = {
        "alert",
        "transaction",
        "pending_simulation",
        "cash_flow_graph",
        "critical_path",
        "reason_codes",
        "model_metadata",
        "rag_evidence",
        "label_evidence",
        "suggested_actions",
        "review",
    }
    for path in detail_files:
        detail = read_json(path)
        missing = sorted(required_detail_sections - set(detail))
        if missing:
            errors.append(f"{path} missing detail sections {missing}")
            break
        if detail["review"].get("state") not in allowed_states:
            errors.append(f"{path} invalid detail review state")
            break
    audit_lines = audit_log_lines(audit_path)
    if audit_lines < len(detail_files):
        errors.append("audit trail has fewer entries than detail views")

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "alert_list_items": len(alerts),
        "detail_views": len(detail_files),
        "audit_trail_lines": audit_lines,
        "allowed_review_states": sorted(allowed_states),
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
