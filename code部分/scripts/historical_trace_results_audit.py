#!/usr/bin/env python3
"""Audit historical trace replay completion across exploit and normal queues."""

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


def report_status(report: Any | None) -> str:
    if report is None:
        return "missing"
    return str(report.get("status", "unknown"))


def audit_one(name: str, report: Any | None, expected_count: int) -> dict[str, Any]:
    if report is None:
        return {
            "name": name,
            "ok": False,
            "state": "missing_report",
            "expected_count": expected_count,
        }
    dry_run = report.get("dry_run") is True
    ok_count = int(report.get("ok_trace_bundles", 0))
    written_count = int(report.get("written_trace_bundles", 0))
    failed_count = int(report.get("failed_trace_bundles", 0))
    queue_count = int(report.get("queue_items_seen", 0))
    replay_paths_missing = [
        item.get("tx_hash")
        for item in report.get("written", [])
        if item.get("trace_status") == "ok" and not item.get("replay_path")
    ]
    ok = (
        not dry_run
        and report.get("status") == "ok"
        and queue_count == expected_count
        and ok_count == expected_count
        and written_count == expected_count
        and failed_count == 0
        and not replay_paths_missing
    )
    if dry_run:
        state = "dry_run_only"
    elif ok:
        state = "complete"
    else:
        state = "incomplete_or_degraded"
    return {
        "name": name,
        "ok": ok,
        "state": state,
        "status": report.get("status"),
        "dry_run": dry_run,
        "expected_count": expected_count,
        "queue_items_seen": queue_count,
        "ok_trace_bundles": ok_count,
        "written_trace_bundles": written_count,
        "failed_trace_bundles": failed_count,
        "replay_paths_missing": replay_paths_missing,
        "method": report.get("method"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit historical trace replay results.")
    parser.add_argument("--exploit-report", default="ops/reports/historical-trace-replay.latest.json")
    parser.add_argument("--normal-report", default="ops/reports/normal-historical-trace-replay.latest.json")
    parser.add_argument("--preflight-report", default="ops/reports/trace-endpoint-preflight.latest.json")
    parser.add_argument("--out", default="ops/reports/historical-trace-results-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    exploit = read_json_or_none(root / args.exploit_report)
    normal = read_json_or_none(root / args.normal_report)
    preflight = read_json_or_none(root / args.preflight_report)
    checks = [
        {
            "name": "trace_endpoint_preflight",
            "ok": report_status(preflight) == "ok",
            "status": report_status(preflight),
            "selected_method": preflight.get("selected_method") if preflight else None,
        },
        audit_one("exploit_historical_trace_replay", exploit, 7),
        audit_one("normal_historical_trace_replay", normal, 50),
    ]
    complete = all(check["ok"] for check in checks)
    dry_run_only = any(check.get("state") == "dry_run_only" for check in checks)
    if complete:
        status = "ok"
    elif dry_run_only:
        status = "awaiting_real_replay"
    else:
        status = "not_ready"
    report = {
        "checked_at": now_iso(),
        "status": status,
        "trace_results_ready": complete,
        "expected_total": 57,
        "ok_total": sum(int(check.get("ok_trace_bundles", 0)) for check in checks),
        "written_total": sum(int(check.get("written_trace_bundles", 0)) for check in checks),
        "failed_total": sum(int(check.get("failed_trace_bundles", 0)) for check in checks),
        "checks": checks,
        "next_action": (
            "run trace_endpoint_preflight then full historical replay with ETH_MAIN_HTTP_URL"
            if status != "ok"
            else "run parser, graph builder, and label promotion review"
        ),
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status in {"ok", "awaiting_real_replay"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
