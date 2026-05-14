#!/usr/bin/env python3
"""Build gray launch readiness report from local artifacts."""

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


def exists(root: Path, path: str) -> bool:
    return (root / path).exists()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build gray launch readiness report.")
    parser.add_argument("--config", default="config/gray_launch.json")
    parser.add_argument("--out", default="ops/reports/gray-launch-readiness.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    config = read_json(root / args.config)
    checks = []
    checks.append(
        {
            "name": "target_protocols_selected",
            "ok": 1 <= len(config.get("target_protocols", [])) <= 3,
            "evidence": config.get("target_protocols", []),
        }
    )
    for severity in ("watch", "high", "critical"):
        checks.append(
            {
                "name": f"{severity}_alerts_enabled",
                "ok": bool(config.get("alert_enablement", {}).get(severity)),
                "evidence": config.get("alert_enablement", {}).get(severity),
            }
        )
    checks.append(
        {
            "name": "no_auto_onchain_execution",
            "ok": config.get("execution_policy", {}).get("auto_onchain_execution") is False,
            "evidence": config.get("execution_policy", {}),
        }
    )
    notifications = config.get("notifications", {})
    for name, item in notifications.items():
        checks.append(
            {
                "name": f"notification_{name}",
                "ok": bool(item.get("configured")),
                "evidence": item,
            }
        )
    checks.append(
        {
            "name": "slo_dashboard_source_reports_exist",
            "ok": all(exists(root, path) for path in config.get("slo_dashboard", {}).get("source_reports", [])),
            "evidence": config.get("slo_dashboard", {}).get("source_reports", []),
        }
    )
    required_docs = [
        "ops/production_runbook.md",
        "ops/weekly_review_template.md",
        "ops/incident_room_template.md",
        "ops/operational_handoff.md",
        "ops/go_no_go_review_packet.md",
    ]
    checks.append(
        {
            "name": "handoff_documents_exist",
            "ok": all(exists(root, path) for path in required_docs),
            "evidence": required_docs,
        }
    )
    failed = [check for check in checks if not check["ok"]]
    report = {
        "checked_at": now_iso(),
        "status": "ready" if not failed else "not_ready",
        "launch_id": config.get("launch_id"),
        "mode": config.get("mode"),
        "checks": checks,
        "blocking_conditions": config.get("blocking_conditions", []),
        "failed_checks": failed,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
