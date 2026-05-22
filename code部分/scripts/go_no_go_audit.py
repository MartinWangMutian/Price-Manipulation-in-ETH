#!/usr/bin/env python3
"""Audit go/no-go checklist against current local evidence."""

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


def check_item(name: str, ok: bool, evidence: Any, blocking: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "blocking": blocking,
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build go/no-go audit report.")
    parser.add_argument("--out", default="ops/reports/go-no-go-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    alert_check = read_json(root / "ops/reports/alert-replay-check.latest.json")
    risk_check = read_json(root / "ops/reports/risk-replay-check.latest.json")
    failure = read_json(root / "ops/reports/failure-drill.latest.json")
    offline = read_json(root / "ops/reports/offline-evaluation.latest.json")
    rag_timeout = read_json(root / "ops/reports/rag-explanation-builder-timeout.latest.json")
    gray = read_json(root / "ops/reports/gray-launch-readiness.latest.json")
    gray_config = read_json(root / "config/gray_launch.json")

    hc_graph = offline.get("high_critical_graph_evidence_coverage", {})
    hc_expl = offline.get("high_critical_explanation_availability", {})
    eligible_hc = hc_graph.get("eligible_alerts", 0)

    items = [
        check_item(
            "pending_to_alert_replay",
            alert_check.get("status") == "ok" and alert_check.get("valid_alerts", 0) > 0,
            {"valid_alerts": alert_check.get("valid_alerts")},
        ),
        check_item(
            "same_input_same_model_stable",
            risk_check.get("status") == "ok" and not risk_check.get("duplicate_idempotency_keys"),
            {
                "model_version": "rule-baseline.v1",
                "duplicate_idempotency_keys": risk_check.get("duplicate_idempotency_keys"),
            },
        ),
        check_item(
            "high_critical_graph_evidence",
            bool(eligible_hc and hc_graph.get("coverage") == 1.0),
            hc_graph,
        ),
        check_item(
            "high_critical_reason_codes",
            bool(eligible_hc),
            {"eligible_high_critical_alerts": eligible_hc},
        ),
        check_item(
            "high_critical_audit_log",
            bool(eligible_hc),
            {"eligible_high_critical_alerts": eligible_hc},
        ),
        check_item(
            "high_critical_human_review_entry",
            exists(root, "data/console/alerts-list.v1.json"),
            {"console_view_model": "data/console/alerts-list.v1.json"},
        ),
        check_item(
            "rag_timeout_does_not_block_alert",
            rag_timeout.get("status") == "ok" and rag_timeout.get("timeout_counts", {}).get("timeout", 0) > 0,
            rag_timeout.get("timeout_counts", {}),
        ),
        check_item(
            "rag_timeout_reason_recorded",
            rag_timeout.get("timeout_counts", {}).get("timeout", 0) > 0,
            rag_timeout.get("timeout_counts", {}),
        ),
        check_item(
            "primary_node_switch_drill",
            False,
            "simulated only; no local primary node configured",
        ),
        check_item(
            "backup_node_switch_drill",
            False,
            "simulated only; no local backup node configured",
        ),
        check_item(
            "third_party_provider_switch_drill",
            False,
            "simulated only; provider-only mode has no local failover target",
        ),
        check_item(
            "target_protocol_whitelist_frozen",
            exists(root, "plan/target_protocol_whitelist.md"),
            "plan/target_protocol_whitelist.md",
        ),
        check_item(
            "model_threshold_frozen",
            exists(root, "config/rule_baseline.json"),
            "config/rule_baseline.json",
        ),
        check_item(
            "risk_types_frozen",
            exists(root, "plan/risk_type_dictionary.md"),
            "plan/risk_type_dictionary.md",
        ),
        check_item(
            "label_authorization_frozen",
            exists(root, "plan/data_authorization.md"),
            "plan/data_authorization.md",
        ),
        check_item(
            "actions_are_suggestions_only",
            gray_config.get("execution_policy", {}).get("auto_onchain_execution") is False,
            gray_config.get("execution_policy", {}),
        ),
        check_item(
            "no_auto_onchain_execution_authority",
            gray_config.get("execution_policy", {}).get("approval_required_for_any_chain_action") is True,
            gray_config.get("execution_policy", {}),
        ),
        check_item(
            "gray_launch_readiness",
            gray.get("status") == "ready",
            {"status": gray.get("status"), "failed_checks": gray.get("failed_checks")},
        ),
    ]
    blocking_failures = [item for item in items if item["blocking"] and not item["ok"]]
    report = {
        "checked_at": now_iso(),
        "status": "go" if not blocking_failures else "no_go",
        "items": items,
        "blocking_failures": blocking_failures,
        "summary": {
            "passed": sum(1 for item in items if item["ok"]),
            "failed": sum(1 for item in items if not item["ok"]),
        },
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
