#!/usr/bin/env python3
"""Validate rag-explanation replay files."""

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
    "graph_summary",
    "doc_summary",
    "analyst_note",
    "evidence_refs",
    "knowledge_snapshot",
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


def load_alert_index(root: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        alert = read_json(path)
        alert_id = alert.get("alert_id")
        if isinstance(alert_id, str) and alert_id not in index:
            index[alert_id] = alert
    return index


def audit_log_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def validate_explanation(
    path: Path,
    explanation: dict[str, Any],
    alert_index: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(explanation))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if explanation.get("schema_ver") != "rag-explanation.v1":
        errors.append("schema_ver mismatch")
    if explanation.get("chain_id") != 1:
        errors.append("chain_id must be 1")
    refs = explanation.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        errors.append("evidence_refs must be non-empty list")
    for field in ("graph_summary", "doc_summary", "analyst_note"):
        value = explanation.get(field)
        if not isinstance(value, str):
            errors.append(f"{field} must be string")
        elif value and "[" not in value:
            errors.append(f"{field} has no inline evidence ref")
    alert = alert_index.get(explanation.get("alert_id"))
    if alert is None:
        errors.append("source alert missing")
    else:
        note = explanation.get("analyst_note", "")
        if f"score {alert['score']}" not in note:
            errors.append("analyst_note does not preserve alert score")
        if f"severity {alert['severity']}" not in note:
            errors.append("analyst_note does not preserve alert severity")
        for reason in alert.get("reasons", []):
            if reason not in note:
                errors.append(f"analyst_note missing reason {reason}")
                break
    if path.name != f"{explanation.get('event_id')}.json":
        errors.append("file name does not match event_id")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rag-explanation replay files.")
    parser.add_argument("--input", default="data/replay/rag-explanation.v1")
    parser.add_argument("--alerts", default="data/replay/alert-event.v1")
    parser.add_argument("--audit-log", default="ops/audit/rag-explanation-builder.jsonl")
    parser.add_argument("--out", default="ops/reports/rag-explanation-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    alert_index = load_alert_index(root / args.alerts)
    files = iter_json_files(root / args.input)
    errors: list[dict[str, Any]] = []
    timeout_counts = Counter()
    valid_explanations = 0
    for path in files:
        try:
            explanation = read_json(path)
            explanation_errors = validate_explanation(path, explanation, alert_index)
            if explanation_errors:
                errors.append({"path": str(path), "errors": explanation_errors})
                continue
            valid_explanations += 1
            timeout_counts["timeout" if explanation.get("timeout") else "ok"] += 1
        except Exception as exc:  # noqa: BLE001 - keep scanning.
            errors.append({"path": str(path), "errors": [str(exc)]})

    audit_lines = audit_log_lines(root / args.audit_log)
    if audit_lines < valid_explanations:
        errors.append(
            {
                "path": args.audit_log,
                "errors": [f"audit log lines {audit_lines} < valid explanations {valid_explanations}"],
            }
        )
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "input": args.input,
        "alerts": args.alerts,
        "files_seen": len(files),
        "valid_explanations": valid_explanations,
        "timeout_counts": dict(sorted(timeout_counts.items())),
        "audit_log": args.audit_log,
        "audit_log_lines": audit_lines,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
