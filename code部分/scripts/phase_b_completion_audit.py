#!/usr/bin/env python3
"""Audit Phase B completion against trace replay and handoff gates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTACT_INPUT_NAMES = {
    "pager_or_feishu_target",
    "phone_or_manual_escalation_target",
    "on_call_analyst",
    "on_call_engineer",
    "incident_commander",
    "protocol_owner_or_partner_contact",
    "multisig_signer_or_authorized_approver",
}

LOCAL_REPLAY_SURFACE_REPORTS = (
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


def ok_check(name: str, ok: bool, evidence: dict[str, Any], owner: str = "project") -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "owner": owner,
        "evidence": evidence,
    }


def read_scope_policy(root: Path, rel_path: str) -> dict[str, Any]:
    policy = read_json_or_none(root / rel_path)
    return policy if isinstance(policy, dict) else {}


def waived_check(name: str, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "ok": True,
        "waived": True,
        "owner": "none",
        "reason": reason,
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Phase B completion gates.")
    parser.add_argument("--scope-policy", default="config/phase_b_scope.json")
    parser.add_argument("--out", default="ops/reports/phase-b-completion-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    scope_policy = read_scope_policy(root, args.scope_policy)
    trace_replay_required = scope_policy.get("trace_replay_required", True) is not False
    ops_contacts_required = scope_policy.get("ops_contacts_required", True) is not False
    training_required = scope_policy.get("training_required", True) is not False
    label_promotion_required = scope_policy.get("label_promotion_required", True) is not False
    project = read_json_or_none(root / "ops/reports/project-status.latest.json")
    required = read_json_or_none(root / "ops/reports/required-inputs-check.latest.json")
    label_readiness = read_json_or_none(root / "ops/reports/label-readiness-audit.latest.json")
    trace_results = read_json_or_none(root / "ops/reports/historical-trace-results-audit.latest.json")
    preflight = read_json_or_none(root / "ops/reports/trace-endpoint-preflight.latest.json")
    promotion = read_json_or_none(root / "ops/reports/label-promotion-audit.latest.json")
    training = read_json_or_none(root / "ops/reports/training-dataset-check.latest.json")
    handoff_path = root / "ops/phase_b_handoff.md"
    post_endpoint_runbook = root / "ops/post_endpoint_trace_runbook.md"

    missing_user_inputs = required.get("missing_user_inputs", []) if required else []
    missing_contact_inputs = [
        item for item in missing_user_inputs if item.get("name") in CONTACT_INPUT_NAMES
    ]
    readiness_gaps = required.get("readiness_gaps", []) if required else []
    pending_promotions = (promotion.get("decision_counts", {}) or {}).get("pending_trace", 0) if promotion else 0
    total_queue_items = int(label_readiness.get("total_trace_queue_items", 0)) if label_readiness else 0
    written_trace_bundles = int(trace_results.get("written_total", 0)) if trace_results else 0
    expected_trace_bundles = int(trace_results.get("expected_total", 0)) if trace_results else 0
    report_statuses = project.get("report_statuses", {}) if project else {}
    missing_local_replay_reports = [
        name for name in LOCAL_REPLAY_SURFACE_REPORTS if report_statuses.get(name) != "ok"
    ]

    if not trace_replay_required:
        checks = [
            ok_check(
                "course_scope_no_paid_api_or_local_node",
                scope_policy.get("mode") == "course_no_trace"
                and scope_policy.get("paid_api_allowed") is False
                and scope_policy.get("local_node_required") is False,
                {
                    "mode": scope_policy.get("mode", "default"),
                    "paid_api_allowed": scope_policy.get("paid_api_allowed"),
                    "local_node_required": scope_policy.get("local_node_required"),
                    "trace_replay_required": trace_replay_required,
                },
            ),
            ok_check(
                "provider_only_shadow_pipeline",
                project is not None and project.get("provider_only_shadow_pipeline") == "ok",
                {"status": project.get("provider_only_shadow_pipeline") if project else "missing"},
            ),
            ok_check(
                "local_replay_surface",
                project is not None and not missing_local_replay_reports,
                {
                    "required_report_statuses": {
                        name: report_statuses.get(name, "missing")
                        for name in LOCAL_REPLAY_SURFACE_REPORTS
                    },
                    "missing_or_not_ok": missing_local_replay_reports,
                },
            ),
            ok_check(
                "report_secret_audit",
                status(read_json_or_none(root / "ops/reports/report-secret-audit.latest.json")) == "ok",
                {
                    "status": status(read_json_or_none(root / "ops/reports/report-secret-audit.latest.json")),
                },
            ),
            ok_check(
                "phase_b_handoff_ready",
                handoff_path.exists(),
                {"handoff": "ops/phase_b_handoff.md" if handoff_path.exists() else "missing"},
            ),
        ]
        if ops_contacts_required:
            checks.append(
                ok_check(
                    "ops_contacts_configured",
                    required is not None and not missing_contact_inputs,
                    {
                        "status": status(required),
                        "missing_contact_inputs": [item.get("name") for item in missing_contact_inputs],
                    },
                    owner="user",
                )
            )
        waived_checks = [
            waived_check(
                "trace_endpoint_preflight_ok",
                "Trace endpoint preflight is outside course_no_trace scope.",
                {"status": status(preflight)},
            ),
            waived_check(
                "historical_trace_replay_complete",
                "Historical trace replay would require a paid trace API or local archive node.",
                {
                    "status": status(trace_results),
                    "written_total": written_trace_bundles,
                    "expected_total": expected_trace_bundles,
                },
            ),
            waived_check(
                "label_promotion_complete",
                "Trace-backed label promotion is outside course_no_trace scope.",
                {
                    "status": status(promotion),
                    "pending_trace": pending_promotions,
                    "promoted_markers": promotion.get("promoted_markers") if promotion else 0,
                },
            ),
            waived_check(
                "training_ready",
                "Training readiness is outside course_no_trace scope.",
                {"status": status(training), "training_ready": training.get("training_ready") if training else None},
            ),
            waived_check(
                "ops_contacts_configured",
                "Production on-call contacts are outside course_no_trace scope.",
                {
                    "required": ops_contacts_required,
                    "missing_contact_inputs": [item.get("name") for item in missing_contact_inputs],
                },
            ),
        ]
        incomplete = [check for check in checks if not check["ok"]]
        user_blockers = [check for check in incomplete if check["owner"] == "user"]
        project_blockers = [check for check in incomplete if check["owner"] != "user"]
        if not incomplete:
            audit_status = "complete"
        elif user_blockers:
            audit_status = "blocked_user_input"
        else:
            audit_status = "blocked_project_work"
        report = {
            "checked_at": now_iso(),
            "status": audit_status,
            "phase_b_complete": not incomplete,
            "completion_target": scope_policy.get("completion_target", "provider_only_course_submission"),
            "scope_policy": args.scope_policy,
            "scope_mode": scope_policy.get("mode", "default"),
            "trace_replay_required": trace_replay_required,
            "checks": checks,
            "waived_checks": waived_checks,
            "missing_checks": [check["name"] for check in incomplete],
            "user_blockers": [check["name"] for check in user_blockers],
            "project_blockers": [check["name"] for check in project_blockers],
            "required_inputs_status": status(required),
            "readiness_gaps": [item.get("name") for item in readiness_gaps],
            "next_user_actions": [],
            "next_project_actions_after_user_inputs": [
                "refresh local reports",
                "use ops/course_submission_summary.md and ops/status_summary.md as course submission evidence",
            ],
        }
        write_json(root / args.out, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    checks = [
        ok_check(
            "provider_only_shadow_pipeline",
            project is not None and project.get("provider_only_shadow_pipeline") == "ok",
            {"status": project.get("provider_only_shadow_pipeline") if project else "missing"},
        ),
        ok_check(
            "label_queue_trace_ready",
            status(label_readiness) == "trace_ready" and total_queue_items == 57,
            {"status": status(label_readiness), "total_trace_queue_items": total_queue_items},
        ),
        ok_check(
            "trace_endpoint_preflight_ok",
            status(preflight) == "ok" and bool(preflight.get("selected_method")) if preflight else False,
            {
                "status": status(preflight),
                "endpoint_configured": preflight.get("endpoint_configured") if preflight else False,
                "selected_method": preflight.get("selected_method") if preflight else None,
            },
            owner="user",
        ),
        ok_check(
            "historical_trace_replay_complete",
            status(trace_results) == "ok" and written_trace_bundles == expected_trace_bundles == 57,
            {
                "status": status(trace_results),
                "written_total": written_trace_bundles,
                "expected_total": expected_trace_bundles,
            },
        ),
        ok_check(
            "label_promotion_complete",
            status(promotion) == "ok" and pending_promotions == 0 and int(promotion.get("promoted_markers", 0)) == 57
            if promotion and label_promotion_required
            else not label_promotion_required,
            {
                "status": status(promotion),
                "pending_trace": pending_promotions,
                "promoted_markers": promotion.get("promoted_markers") if promotion else 0,
                "required": label_promotion_required,
            },
            owner="user",
        ),
        ok_check(
            "training_ready",
            status(training) == "ok" and training.get("training_ready") is True
            if training and training_required
            else not training_required,
            {
                "status": status(training),
                "training_ready": training.get("training_ready") if training else None,
                "required": training_required,
            },
        ),
        ok_check(
            "ops_contacts_configured",
            required is not None and not missing_contact_inputs if ops_contacts_required else True,
            {
                "status": status(required),
                "missing_contact_inputs": [item.get("name") for item in missing_contact_inputs],
                "required": ops_contacts_required,
            },
            owner="user",
        ),
        ok_check(
            "phase_b_handoff_ready",
            handoff_path.exists() and post_endpoint_runbook.exists(),
            {
                "handoff": "ops/phase_b_handoff.md" if handoff_path.exists() else "missing",
                "post_endpoint_runbook": "ops/post_endpoint_trace_runbook.md" if post_endpoint_runbook.exists() else "missing",
            },
        ),
    ]

    incomplete = [check for check in checks if not check["ok"]]
    user_blockers = [check for check in incomplete if check["owner"] == "user"]
    project_blockers = [check for check in incomplete if check["owner"] != "user"]
    if not incomplete:
        audit_status = "complete"
    elif user_blockers:
        audit_status = "blocked_user_input"
    else:
        audit_status = "blocked_project_work"

    report = {
        "checked_at": now_iso(),
        "status": audit_status,
        "phase_b_complete": not incomplete,
        "completion_target": scope_policy.get("completion_target", "full_trace_replay"),
        "scope_policy": args.scope_policy,
        "scope_mode": scope_policy.get("mode", "default"),
        "trace_replay_required": trace_replay_required,
        "checks": checks,
        "missing_checks": [check["name"] for check in incomplete],
        "user_blockers": [check["name"] for check in user_blockers],
        "project_blockers": [check["name"] for check in project_blockers],
        "required_inputs_status": status(required),
        "readiness_gaps": [item.get("name") for item in readiness_gaps],
        "next_user_actions": [
            "provide ETH_MAIN_HTTP_URL or pass provider trace capability probe",
            "fill config/ops_contacts.local.json and export OPS_CONTACTS_CONFIG",
            "after real trace replay, analyst-promote exploit and normal label decisions",
        ],
        "next_project_actions_after_user_inputs": [
            "run trace endpoint preflight",
            "run exploit and normal historical trace replay",
            "parse traces, rebuild protocol features and cash-flow graphs",
            "audit and promote labels, then refresh training dataset readiness",
        ],
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
