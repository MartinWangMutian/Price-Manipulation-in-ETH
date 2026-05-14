#!/usr/bin/env python3
"""Validate alert-event replay files and audit log coverage."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "event_id",
    "schema_ver",
    "chain_id",
    "created_at",
    "idempotency_key",
    "alert_id",
    "tx_hash",
    "score",
    "severity",
    "reasons",
    "evidence_refs",
    "suggested_actions",
    "alert_version",
}


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


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def expected_severity(score: float) -> str:
    if score > 0.9:
        return "critical"
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "watch"
    return "low"


def validate_alert(path: Path, alert: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(alert))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if alert.get("schema_ver") != "alert-event.v1":
        errors.append("schema_ver mismatch")
    if alert.get("chain_id") != 1:
        errors.append("chain_id must be 1")
    score = alert.get("score")
    if not isinstance(score, (int, float)) or score < 0 or score > 1:
        errors.append("score must be number in [0,1]")
    elif alert.get("severity") != expected_severity(float(score)):
        errors.append("severity does not match default router thresholds")
    refs = alert.get("evidence_refs")
    if not isinstance(refs, list) or not any(str(ref).startswith("graph:") for ref in refs):
        errors.append("missing graph evidence ref")
    if not isinstance(refs, list) or not any(str(ref).startswith("trace:") for ref in refs):
        errors.append("missing trace evidence ref")
    if not isinstance(refs, list) or not any(str(ref).startswith("label:") for ref in refs):
        errors.append("missing label evidence ref")
    if not isinstance(alert.get("suggested_actions"), list):
        errors.append("suggested_actions must be list")
    if path.name != f"{alert.get('event_id')}.json":
        errors.append("file name does not match event_id")
    return errors


def audit_log_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate alert replay files.")
    parser.add_argument("--input", default="data/replay/alert-event.v1")
    parser.add_argument("--audit-log", default="ops/audit/alert-orchestrator.jsonl")
    parser.add_argument("--out", default="ops/reports/alert-replay-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    files = iter_json_files(root / args.input)
    errors: list[dict[str, Any]] = []
    idempotency_counts = Counter()
    severity_counts = Counter()
    action_counts = Counter()
    valid_alerts = 0
    for path in files:
        try:
            alert = read_json(path)
            alert_errors = validate_alert(path, alert)
            if alert_errors:
                errors.append({"path": str(path), "errors": alert_errors})
                continue
            valid_alerts += 1
            idempotency_counts[alert["idempotency_key"]] += 1
            severity_counts[alert["severity"]] += 1
            for action in alert["suggested_actions"]:
                action_counts[action] += 1
        except Exception as exc:  # noqa: BLE001 - keep scanning.
            errors.append({"path": str(path), "errors": [str(exc)]})

    duplicate_keys = sorted(key for key, count in idempotency_counts.items() if count > 1)
    audit_lines = audit_log_lines(root / args.audit_log)
    if audit_lines < valid_alerts:
        errors.append(
            {
                "path": args.audit_log,
                "errors": [f"audit log lines {audit_lines} < valid alerts {valid_alerts}"],
            }
        )
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors and not duplicate_keys else "failed",
        "input": args.input,
        "audit_log": args.audit_log,
        "audit_log_lines": audit_lines,
        "files_seen": len(files),
        "valid_alerts": valid_alerts,
        "unique_idempotency_keys": len(idempotency_counts),
        "duplicate_idempotency_keys": duplicate_keys,
        "severity_counts": dict(sorted(severity_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
