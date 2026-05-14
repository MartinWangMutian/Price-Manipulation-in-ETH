#!/usr/bin/env python3
"""Aggregate project status and blockers from local reports."""

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


def report_status(root: Path, path: str) -> Any:
    full = root / path
    if not full.exists():
        return {"missing": True}
    data = read_json(full)
    return data.get("status", "unknown")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate project status.")
    parser.add_argument("--out", default="ops/reports/project-status.latest.json")
    parser.add_argument("--blockers", default="ops/blocker_register.md")
    args = parser.parse_args()

    root = Path.cwd()
    reports = {
        "pending_replay": "ops/reports/pending-replay-check-p2a.latest.json",
        "trace_replay": "ops/reports/trace-replay-check-p2b-deduped.latest.json",
        "trace_audit": "ops/reports/trace-bundle-audit.latest.json",
        "graph_replay": "ops/reports/graph-replay-check.latest.json",
        "risk_replay": "ops/reports/risk-replay-check.latest.json",
        "alert_replay": "ops/reports/alert-replay-check.latest.json",
        "rag_explanation": "ops/reports/rag-explanation-check.latest.json",
        "console_view": "ops/reports/analyst-console-view-check.latest.json",
        "offline_eval": "ops/reports/offline-evaluation.latest.json",
        "failure_drill": "ops/reports/failure-drill.latest.json",
        "gray_launch": "ops/reports/gray-launch-readiness.latest.json",
        "go_no_go": "ops/reports/go-no-go-audit.latest.json",
        "validation_metrics": "ops/reports/validation-metrics-audit.latest.json",
        "required_inputs": "ops/reports/required-inputs-check.latest.json",
    }
    statuses = {name: report_status(root, path) for name, path in reports.items()}
    provider_shadow_ok = all(
        statuses.get(name) == "ok"
        for name in (
            "pending_replay",
            "trace_audit",
            "graph_replay",
            "risk_replay",
            "alert_replay",
            "rag_explanation",
            "console_view",
            "offline_eval",
            "failure_drill",
        )
    )
    blockers = [
        {
            "id": "live_trace_endpoint",
            "owner": "user",
            "needed": "Geth or Erigon trace HTTP endpoint",
            "unblocks": ["real trace P95", "rich graph edges", "high/critical evidence", "GraphSAGE training data"],
        },
        {
            "id": "ops_contacts",
            "owner": "user",
            "needed": "Pager/Feishu, phone/manual escalation, on-call and approver names",
            "unblocks": ["gray launch readiness", "operational handoff", "production go/no-go"],
        },
        {
            "id": "labeled_replay_sets",
            "owner": "project",
            "needed": "confirmed exploit tx hashes and normal complex transaction set",
            "unblocks": ["false positive/negative metrics", "lead time", "GraphSAGE evaluation"],
        },
        {
            "id": "live_failover_drill",
            "owner": "project",
            "needed": "primary/backup/provider switch test with real endpoints",
            "unblocks": ["go/no-go failover checks", "Phase 6 gate"],
        },
    ]
    status = {
        "checked_at": now_iso(),
        "provider_only_shadow_pipeline": "ok" if provider_shadow_ok else "not_ok",
        "production_go_no_go": statuses.get("go_no_go"),
        "validation_metrics": statuses.get("validation_metrics"),
        "required_inputs": statuses.get("required_inputs"),
        "gray_launch_readiness": statuses.get("gray_launch"),
        "report_statuses": statuses,
        "blockers": blockers,
        "next_actions": [
            "configure Geth/Erigon trace endpoint",
            "fill operations contact roster",
            "review key transaction hashes for seed incidents",
            "run live failover drills",
        ],
    }
    write_json(root / args.out, status)

    blocker_md = ["# Blocker Register", "", f"Updated: {now_iso()}", ""]
    for blocker in blockers:
        blocker_md.extend(
            [
                f"## {blocker['id']}",
                "",
                f"- Owner: {blocker['owner']}",
                f"- Needed: {blocker['needed']}",
                f"- Unblocks: {', '.join(blocker['unblocks'])}",
                "",
            ]
        )
    (root / args.blockers).write_text("\n".join(blocker_md), encoding="utf-8")
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
