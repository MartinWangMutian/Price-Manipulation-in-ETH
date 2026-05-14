#!/usr/bin/env python3
"""Validate seed training dataset manifests."""

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate training dataset seed manifests.")
    parser.add_argument("--incidents", default="data/training/positive_incidents.seed.json")
    parser.add_argument("--snapshot", default="data/training/label_snapshot.v1.json")
    parser.add_argument("--splits-dir", default="data/training/splits")
    parser.add_argument("--unlabeled", default="data/training/unlabeled_pool.provider_only.v1.json")
    parser.add_argument("--out", default="ops/reports/training-dataset-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    incidents = read_json(root / args.incidents).get("incidents", [])
    snapshot = read_json(root / args.snapshot)
    unlabeled = read_json(root / args.unlabeled).get("items", [])
    errors: list[str] = []
    incident_ids = set()
    missing_tx = []
    for incident in incidents:
        incident_id = incident.get("incident_id")
        if not incident_id:
            errors.append("incident missing incident_id")
            continue
        if incident_id in incident_ids:
            errors.append(f"duplicate incident_id {incident_id}")
        incident_ids.add(incident_id)
        for field in ("chain", "incident_date", "attack_type", "affected_protocol"):
            if not incident.get(field):
                errors.append(f"{incident_id} missing {field}")
        if not incident.get("source_refs"):
            errors.append(f"{incident_id} missing source_refs")
        if not incident.get("key_transactions"):
            missing_tx.append(incident_id)

    split_ids: set[str] = set()
    split_counts = {}
    for split_name in ("train", "validation", "replay"):
        path = root / args.splits_dir / f"{split_name}.v1.json"
        if not path.exists():
            errors.append(f"missing split file {path}")
            continue
        split = read_json(path)
        items = split.get("items", [])
        split_counts[split_name] = len(items)
        for item in items:
            incident_id = item.get("incident_id")
            if incident_id in split_ids:
                errors.append(f"incident appears in multiple splits: {incident_id}")
            split_ids.add(incident_id)
    if split_ids != incident_ids:
        errors.append("split incident ids do not match seed incident ids")

    if snapshot.get("positive_incidents") != len(incidents):
        errors.append("snapshot positive_incidents count mismatch")
    if snapshot.get("unlabeled_provider_only_graphs") != len(unlabeled):
        errors.append("snapshot unlabeled count mismatch")
    if snapshot.get("training_ready") is not False:
        errors.append("seed dataset should remain training_ready=false until graph replay labels exist")

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "positive_incidents": len(incidents),
        "split_counts": split_counts,
        "unlabeled_provider_only_graphs": len(unlabeled),
        "missing_key_transaction_incidents": sorted(missing_tx),
        "training_ready": snapshot.get("training_ready"),
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
