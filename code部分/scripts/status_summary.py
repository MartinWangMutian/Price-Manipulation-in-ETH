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
    contacts_bootstrap = read_json_or_none(root / "ops/reports/ops-contacts-bootstrap.latest.json")
    env_local = read_json_or_none(root / "ops/reports/env-local-audit.latest.json")
    provider_probe = read_json_or_none(root / "ops/reports/provider-trace-capability-probe.latest.json")
    provider_probe_plan = read_json_or_none(root / "ops/reports/provider-trace-capability-probe.plan.json")
    secret_audit = read_json_or_none(root / "ops/reports/report-secret-audit.latest.json")
    manifest = read_json_or_none(root / "ops/reports/artifact-manifest.latest.json")
    phase_b = read_json_or_none(root / "ops/reports/phase-b-completion-audit.latest.json")
    next_action = read_json_or_none(root / "ops/reports/phase-b-next-action.latest.json")
    replay_candidates = read_json_or_none(root / "ops/reports/replay-label-candidates-check.latest.json")
    trace_queue = read_json_or_none(root / "ops/reports/trace-replay-queue-builder.latest.json")
    trace_preflight_plan = read_json_or_none(root / "ops/reports/trace-endpoint-preflight.plan.json")
    trace_preflight = read_json_or_none(root / "ops/reports/trace-endpoint-preflight.latest.json")
    historical_trace = read_json_or_none(root / "ops/reports/historical-trace-replay.latest.json")
    normal_candidates = read_json_or_none(root / "ops/reports/normal-replay-candidates-check.latest.json")
    normal_trace = read_json_or_none(root / "ops/reports/normal-historical-trace-replay.latest.json")
    trace_results = read_json_or_none(root / "ops/reports/historical-trace-results-audit.latest.json")
    label_readiness = read_json_or_none(root / "ops/reports/label-readiness-audit.latest.json")
    label_promotion = read_json_or_none(root / "ops/reports/label-promotion-audit.latest.json")
    training_check = read_json_or_none(root / "ops/reports/training-dataset-check.latest.json")
    scope_policy = read_json_or_none(root / "config/phase_b_scope.json") or {}
    trace_replay_required = scope_policy.get("trace_replay_required", True) is not False

    report_statuses = project.get("report_statuses", {}) if project else {}
    blockers = project.get("blockers", []) if project else []
    counts = manifest.get("counts", {}) if manifest else {}

    lines = [
        "# Project Status Summary",
        "",
        f"Generated: {now_iso()}",
        "",
        "Handoff: ops/phase_b_handoff.md",
        "User action packet: ops/phase_b_user_action_packet.md",
        "Completion checklist: ops/phase_b_completion_checklist.md",
        "",
        "## Current Readiness",
        "",
        f"- Scope mode: {scope_policy.get('mode', 'default')}",
        f"- Trace replay required: {trace_replay_required}",
        f"- Provider-only shadow pipeline: {project.get('provider_only_shadow_pipeline', 'missing') if project else 'missing'}",
        f"- Production go/no-go: {status_value(go_no_go)}"
        + (" (out of scope)" if not trace_replay_required else ""),
        f"- Validation metrics: {status_value(validation)}"
        + (" (out of scope)" if not trace_replay_required else ""),
        f"- Required inputs: {status_value(required)}",
        f"- Env local: {status_value(env_local)}",
        f"- Provider trace probe: {status_value(provider_probe) if provider_probe else 'not_run'}",
        f"- Report secret audit: {status_value(secret_audit)}",
        f"- Phase B completion: {project.get('phase_b_completion', status_value(phase_b)) if project else status_value(phase_b)}",
        f"- Phase B next action: {next_action.get('selected_action', {}).get('action_id', 'missing') if next_action else 'missing'}",
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
    if go_failures and trace_replay_required:
        lines.extend(["", "## Go/No-Go Failures", ""])
        for name in go_failures:
            lines.append(f"- {name}")
    elif go_failures:
        lines.extend(["", "## Out-Of-Scope Production Gaps", ""])
        lines.append("- Production go/no-go failures are retained for reference only and are waived for course_no_trace scope.")

    validation_failures = metric_failures(validation)
    if validation_failures and trace_replay_required:
        lines.extend(["", "## Metric Gaps", ""])
        for failure in validation_failures:
            lines.append(f"- {failure}")
    elif validation_failures:
        lines.extend(["", "## Out-Of-Scope Metric Gaps", ""])
        lines.append("- Training/live-SLO metric gaps are retained for reference only and are waived for course_no_trace scope.")

    if phase_b:
        lines.extend(["", "## Phase B Completion Audit", ""])
        lines.append(f"- Complete: {phase_b.get('phase_b_complete')}")
        missing_checks = phase_b.get("missing_checks", [])
        if missing_checks:
            lines.append(f"- Missing checks: {', '.join(missing_checks)}")
        user_blockers = phase_b.get("user_blockers", [])
        if user_blockers:
            lines.append(f"- User blockers: {', '.join(user_blockers)}")
        project_blockers = phase_b.get("project_blockers", [])
        if project_blockers:
            lines.append(f"- Project blockers: {', '.join(project_blockers)}")

    if env_local:
        lines.extend(["", "## Env Local Audit", ""])
        lines.append(f"- Provider ready: {env_local.get('provider_ready')}")
        lines.append(f"- Main trace ready: {env_local.get('main_trace_ready')}")
        invalid = [
            check.get("name", "unknown")
            for check in env_local.get("checks", [])
            if check.get("present") and not check.get("ok")
        ]
        if invalid:
            lines.append(f"- Invalid URL checks: {', '.join(invalid)}")

    if provider_probe or provider_probe_plan:
        lines.extend(["", "## Provider Trace Probe", ""])
        if provider_probe:
            lines.append(f"- Latest status: {provider_probe.get('status', 'unknown')}")
            selected_method = provider_probe.get("selected_method")
            if selected_method:
                lines.append(f"- Selected method: {selected_method}")
        if provider_probe_plan:
            lines.append(f"- Dry-run plan: {provider_probe_plan.get('status', 'unknown')}")
            provider_check = provider_probe_plan.get("provider_http_check", {})
            host = provider_check.get("host")
            if host:
                lines.append(f"- Provider host: {host}")

    if trace_preflight_plan:
        lines.extend(["", "## Main Trace Endpoint Plan", ""])
        if not trace_replay_required:
            lines.append("- Scope: waived for course_no_trace")
        lines.append(f"- Dry-run plan: {trace_preflight_plan.get('status', 'unknown')}")
        main_check = trace_preflight_plan.get("main_trace_http_check", {})
        if main_check:
            lines.append(f"- ETH_MAIN_HTTP_URL present: {main_check.get('present')}")
            lines.append(f"- ETH_MAIN_HTTP_URL ok: {main_check.get('ok')}")

    if secret_audit:
        lines.extend(["", "## Report Secret Audit", ""])
        lines.append(f"- Scanned files: {secret_audit.get('scanned_files', 0)}")
        lines.append(f"- Findings: {len(secret_audit.get('findings', []))}")

    if contacts_bootstrap:
        lines.extend(["", "## Ops Contacts Bootstrap", ""])
        lines.append(f"- Status: {contacts_bootstrap.get('status', 'unknown')}")
        lines.append(f"- Local file git-ignored: {contacts_bootstrap.get('git_ignored')}")
        next_contact_action = contacts_bootstrap.get("next_action")
        if next_contact_action and trace_replay_required:
            lines.append(f"- Next action: {next_contact_action}")
        elif next_contact_action:
            lines.append("- Scope: optional for course_no_trace")

    if next_action:
        selected = next_action.get("selected_action", {})
        lines.extend(["", "## Phase B Next Action", ""])
        lines.append(f"- Action: {selected.get('action_id', 'unknown')}")
        lines.append(f"- Owner: {selected.get('owner', 'unknown')}")
        reason = selected.get("reason")
        if reason:
            lines.append(f"- Reason: {reason}")

    if replay_candidates or training_check:
        lines.extend(["", "## Training Label Backlog", ""])
        if not trace_replay_required:
            lines.append("- Scope note: trace replay, trace-backed promotion, and training readiness are waived for this course assignment.")
        if replay_candidates:
            missing = replay_candidates.get("missing_ethereum_candidate_incidents", [])
            lines.append(f"- Candidate transaction incidents: {replay_candidates.get('positive_candidate_incidents', 0)}")
            lines.append(f"- Candidate transactions: {replay_candidates.get('candidate_transactions', 0)}")
            lines.append(f"- Missing Ethereum candidate incidents: {', '.join(missing) if missing else 'none'}")
            lines.append(
                "- Normal complex set: "
                f"{replay_candidates.get('normal_complex_strategy_status', 'unknown')} "
                f"({replay_candidates.get('normal_complex_required_count', 0)} required)"
            )
        if trace_queue:
            lines.append(f"- Historical trace replay queue: {trace_queue.get('queue_items', 0)} items")
        if trace_preflight:
            lines.append(f"- Trace endpoint preflight: {trace_preflight.get('status', 'unknown')}")
        if historical_trace:
            lines.append(f"- Historical exploit replay status: {historical_trace.get('status', 'unknown')}")
            lines.append(
                "- Historical exploit replay persisted: "
                f"{historical_trace.get('written_trace_bundles', 0)} "
                f"(ok={historical_trace.get('ok_trace_bundles', 0)}, "
                f"failed={historical_trace.get('failed_trace_bundles', 0)})"
            )
        if normal_candidates:
            lines.append(f"- Normal candidate transactions: {normal_candidates.get('candidate_count', 0)}")
            lines.append(f"- Normal candidate check: {normal_candidates.get('status', 'unknown')}")
            bucket_counts = normal_candidates.get("bucket_counts", {})
            if bucket_counts:
                rendered = ", ".join(f"{name}={count}" for name, count in sorted(bucket_counts.items()))
                lines.append(f"- Normal candidate buckets: {rendered}")
        if normal_trace:
            lines.append(f"- Normal trace replay status: {normal_trace.get('status', 'unknown')}")
            lines.append(
                "- Normal trace replay persisted: "
                f"{normal_trace.get('written_trace_bundles', 0)} "
                f"(ok={normal_trace.get('ok_trace_bundles', 0)}, "
                f"failed={normal_trace.get('failed_trace_bundles', 0)})"
            )
        if trace_results:
            lines.append(f"- Historical trace results: {trace_results.get('status', 'unknown')}")
            lines.append(f"- Persisted trace bundles: {trace_results.get('written_total', 0)} / {trace_results.get('expected_total', 0)}")
        if label_readiness:
            lines.append(f"- Label queue readiness: {label_readiness.get('status', 'unknown')}")
            lines.append(f"- Total trace queue items: {label_readiness.get('total_trace_queue_items', 0)}")
        if label_promotion:
            lines.append(f"- Pending promotion decisions: {label_promotion.get('decision_counts', {}).get('pending_trace', 0)}")
            lines.append(f"- Promoted labels: {label_promotion.get('promoted_markers', 0)}")
        if training_check:
            lines.append(f"- Training dataset check: {training_check.get('status', 'unknown')}")
            lines.append(f"- Training ready: {training_check.get('training_ready')}")

    if required:
        missing_user_inputs = required.get("missing_user_inputs", required.get("missing", []))
        if missing_user_inputs:
            lines.extend(["", "## Inputs Needed From User", ""])
            for item in missing_user_inputs:
                name = item.get("name", "unknown")
                needed_for = ", ".join(item.get("needed_for", []))
                source = item.get("source", "unknown")
                lines.append(f"- {name}: {needed_for} (source: {source})")
        readiness_gaps = required.get("readiness_gaps", [])
        if readiness_gaps:
            lines.extend(["", "## Phase B Readiness Gaps", ""])
            for item in readiness_gaps:
                name = item.get("name", "unknown")
                observed = item.get("observed_status")
                needed_for = ", ".join(item.get("needed_for", []))
                source = item.get("source", "unknown")
                detail = f"observed={observed}, " if observed is not None else ""
                lines.append(f"- {name}: {detail}{needed_for} (source: {source})")

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
            "python3 scripts/phase_b_refresh.py \\",
            "  --out ops/reports/phase-b-refresh.latest.json",
            "",
            "python3 scripts/ops_contacts_bootstrap.py \\",
            "  --report ops/reports/ops-contacts-bootstrap.latest.json",
            "",
            "python3 scripts/required_inputs_check.py \\",
            "  --contacts \"${OPS_CONTACTS_CONFIG:-config/ops_contacts.local.json}\" \\",
            "  --out ops/reports/required-inputs-check.latest.json",
            "",
            "python3 scripts/env_local_audit.py \\",
            "  --env-file .env.local \\",
            "  --out ops/reports/env-local-audit.latest.json",
            "",
            "python3 scripts/report_secret_audit.py \\",
            "  --input ops/reports \\",
            "  --out ops/reports/report-secret-audit.latest.json",
            ]
        )
    if trace_replay_required and label_readiness and label_readiness.get("status") == "trace_ready":
        lines.extend(
            [
                "",
                "# Optional: test whether ETH_PROVIDER_HTTP_URL can satisfy historical trace replay.",
                "python3 scripts/provider_trace_capability_probe.py \\",
                "  --env-file .env.local \\",
                "  --queue data/training/trace_replay_queue.v1.json \\",
                "  --method auto \\",
                "  --out ops/reports/provider-trace-capability-probe.latest.json",
            "",
            "# Standard Phase B trace endpoint preflight; requires ETH_MAIN_HTTP_URL.",
            "python3 scripts/main_trace_endpoint_preflight.py \\",
            "  --env-file .env.local \\",
            "  --queue data/training/trace_replay_queue.v1.json \\",
            "  --method auto \\",
            "  --out ops/reports/trace-endpoint-preflight.latest.json",
                "",
                "python3 scripts/historical_trace_replay.py \\",
                "  --queue data/training/trace_replay_queue.v1.json \\",
                "  --method auto \\",
                "  --out ops/reports/historical-trace-replay.latest.json",
                "",
                "python3 scripts/historical_trace_replay.py \\",
                "  --queue data/training/normal_trace_replay_queue.v1.json \\",
                "  --method auto \\",
                "  --out ops/reports/normal-historical-trace-replay.latest.json",
                "",
                "python3 scripts/label_readiness_audit.py \\",
                "  --out ops/reports/label-readiness-audit.latest.json",
            ]
        )
    lines.extend(
        [
            "",
            "python3 scripts/project_status_audit.py \\",
            "  --out ops/reports/project-status.latest.json \\",
            "  --blockers ops/blocker_register.md",
            "",
            "python3 scripts/phase_b_completion_audit.py \\",
            "  --out ops/reports/phase-b-completion-audit.latest.json",
            "",
            "python3 scripts/phase_b_next_action.py \\",
            "  --out ops/reports/phase-b-next-action.latest.json",
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
