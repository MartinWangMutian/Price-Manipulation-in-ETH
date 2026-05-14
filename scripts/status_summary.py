#!/usr/bin/env python3
"""Generate a concise Markdown status page from local audit reports."""

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


def status_value(report: Any | None) -> str:
    if report is None:
        return "missing"
    return str(report.get("status", "unknown"))


def first_blocking_names(report: Any | None, limit: int = 6) -> list[str]:
    if not report:
        return []
    failures = report.get("blocking_failures") or []
    names = [str(item.get("name", "unknown")) for item in failures]
    return names[:limit]


def metric_failures(report: Any | None, limit: int = 8) -> list[str]:
    if not report:
        return []
    failures = []
    for metric in report.get("metrics", []):
        if not metric.get("ok"):
            note = metric.get("note") or "not passing"
            failures.append(f"{metric.get('name', 'unknown')}: {note}")
    return failures[:limit]


def render_summary(root: Path) -> str:
    project = read_json_or_none(root / "ops/reports/project-status.latest.json")
    go_no_go = read_json_or_none(root / "ops/reports/go-no-go-audit.latest.json")
    validation = read_json_or_none(root / "ops/reports/validation-metrics-audit.latest.json")
    required = read_json_or_none(root / "ops/reports/required-inputs-check.latest.json")
    manifest = read_json_or_none(root / "ops/reports/artifact-manifest.latest.json")

    report_statuses = project.get("report_statuses", {}) if project else {}
    blockers = project.get("blockers", []) if project else []
    counts = manifest.get("counts", {}) if manifest else {}

    lines = [
        "# Project Status Summary",
        "",
        f"Generated: {now_iso()}",
        "",
        "## Current Readiness",
        "",
        f"- Provider-only shadow pipeline: {project.get('provider_only_shadow_pipeline', 'missing') if project else 'missing'}",
        f"- Production go/no-go: {status_value(go_no_go)}",
        f"- Validation metrics: {status_value(validation)}",
        f"- Required inputs: {status_value(required)}",
        f"- Gray launch readiness: {project.get('gray_launch_readiness', 'missing') if project else 'missing'}",
        "",
        "## Passing Local Replay Surface",
        "",
    ]
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
    ):
        lines.append(f"- {name}: {report_statuses.get(name, 'missing')}")

    lines.extend(["", "## Blocking Items", ""])
    for blocker in blockers:
        lines.append(f"- {blocker.get('id')}: {blocker.get('needed')} (owner: {blocker.get('owner')})")
    if not blockers:
        lines.append("- none recorded")

    go_failures = first_blocking_names(go_no_go)
    if go_failures:
        lines.extend(["", "## Go/No-Go Failures", ""])
        for name in go_failures:
            lines.append(f"- {name}")

    validation_failures = metric_failures(validation)
    if validation_failures:
        lines.extend(["", "## Metric Gaps", ""])
        for failure in validation_failures:
            lines.append(f"- {failure}")

    if required:
        missing = required.get("missing", [])
        if missing:
            lines.extend(["", "## Inputs Needed From User", ""])
            for item in missing:
                lines.append(f"- {item}")

    if counts:
        lines.extend(["", "## Artifact Counts", ""])
        for name in sorted(counts):
            lines.append(f"- {name}: {counts[name]}")

    lines.extend(
        [
            "",
            "## Next Commands",
            "",
            "```bash",
            "python3 scripts/required_inputs_check.py \\",
            "  --contacts \"${OPS_CONTACTS_CONFIG:-config/ops_contacts.example.json}\" \\",
            "  --out ops/reports/required-inputs-check.latest.json",
            "",
            "python3 scripts/project_status_audit.py \\",
            "  --out ops/reports/project-status.latest.json \\",
            "  --blockers ops/blocker_register.md",
            "",
            "python3 scripts/status_summary.py \\",
            "  --out ops/status_summary.md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate concise project status Markdown.")
    parser.add_argument("--out", default="ops/status_summary.md")
    args = parser.parse_args()

    root = Path.cwd()
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_summary(root), encoding="utf-8")
    print(json.dumps({"status": "ok", "out": args.out}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
