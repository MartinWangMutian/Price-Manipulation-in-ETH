#!/usr/bin/env python3
"""Validate risk-score replay files."""

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
    "tx_hash",
    "score",
    "severity",
    "reasons",
    "model_version",
    "feature_ver",
    "threshold_profile",
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


def validate_record(path: Path, record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if record.get("schema_ver") != "risk-score.v1":
        errors.append("schema_ver mismatch")
    if record.get("chain_id") != 1:
        errors.append("chain_id must be 1")
    score = record.get("score")
    if not isinstance(score, (int, float)) or score < 0 or score > 1:
        errors.append("score must be number in [0,1]")
    elif record.get("severity") != expected_severity(float(score)):
        errors.append("severity does not match default threshold profile")
    if not isinstance(record.get("reasons"), list):
        errors.append("reasons must be list")
    if path.name != f"{record.get('event_id')}.json":
        errors.append("file name does not match event_id")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate risk-score replay files.")
    parser.add_argument("--input", default="data/replay/risk-score.v1")
    parser.add_argument("--out", default="ops/reports/risk-replay-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    files = iter_json_files(root / args.input)
    errors: list[dict[str, Any]] = []
    idempotency_counts = Counter()
    severity_counts = Counter()
    reason_counts = Counter()
    valid_scores = 0
    for path in files:
        try:
            record = read_json(path)
            record_errors = validate_record(path, record)
            if record_errors:
                errors.append({"path": str(path), "errors": record_errors})
                continue
            valid_scores += 1
            idempotency_counts[record["idempotency_key"]] += 1
            severity_counts[record["severity"]] += 1
            for reason in record["reasons"]:
                reason_counts[reason] += 1
        except Exception as exc:  # noqa: BLE001 - keep scanning.
            errors.append({"path": str(path), "errors": [str(exc)]})

    duplicate_keys = sorted(key for key, count in idempotency_counts.items() if count > 1)
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors and not duplicate_keys else "failed",
        "input": args.input,
        "files_seen": len(files),
        "valid_scores": valid_scores,
        "unique_idempotency_keys": len(idempotency_counts),
        "duplicate_idempotency_keys": duplicate_keys,
        "severity_counts": dict(sorted(severity_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
