#!/usr/bin/env python3
"""Build seed training dataset manifests from incident labels and replay graphs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
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


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def split_for(incident_id: str, ratios: dict[str, float]) -> str:
    bucket = int(hashlib.sha256(incident_id.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    train_cut = ratios["train"]
    validation_cut = train_cut + ratios["validation"]
    if bucket < train_cut:
        return "train"
    if bucket < validation_cut:
        return "validation"
    return "replay"


def provider_unlabeled_graphs(graph_root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in iter_json_files(graph_root):
        graph = read_json(path)
        flags = set(graph.get("feature_missing_flags", []))
        if "trace_unsupported" in flags:
            items.append(
                {
                    "tx_hash": graph.get("tx_hash"),
                    "graph_event_id": graph.get("event_id"),
                    "graph_path": str(path),
                    "reason": "provider_only_trace_unsupported",
                }
            )
    return items


def label_candidates(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    payload = read_json(path)
    by_incident: dict[str, list[str]] = {}
    for item in payload.get("positive_candidates", []):
        tx_hashes = [
            tx["tx_hash"]
            for tx in item.get("candidate_transactions", [])
            if tx.get("tx_hash")
        ]
        if tx_hashes:
            by_incident[item["incident_id"]] = tx_hashes
    return by_incident


def main() -> int:
    parser = argparse.ArgumentParser(description="Build training dataset seed manifests.")
    parser.add_argument("--incidents", default="data/training/positive_incidents.seed.json")
    parser.add_argument("--split-policy", default="config/training_split_policy.json")
    parser.add_argument("--graph-input", default="data/replay/graph-inference.v1")
    parser.add_argument("--label-candidates", default="data/training/replay_label_candidates.seed.json")
    parser.add_argument("--out-dir", default="data/training")
    parser.add_argument("--report", default="ops/reports/training-dataset-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    incidents_payload = read_json(root / args.incidents)
    split_policy = read_json(root / args.split_policy)
    candidates_by_incident = label_candidates(root / args.label_candidates)
    incidents = incidents_payload.get("incidents", [])
    ratios = split_policy["split_ratios"]
    splits = {"train": [], "validation": [], "replay": []}
    status_counts = Counter()
    chain_counts = Counter()
    attack_counts = Counter()
    missing_key_tx = []

    for incident in incidents:
        incident_id = incident["incident_id"]
        split = split_for(incident_id, ratios)
        item = {
            "incident_id": incident_id,
            "label": 1,
            "chain": incident["chain"],
            "attack_type": incident["attack_type"],
            "affected_protocol": incident["affected_protocol"],
            "key_transactions": incident.get("key_transactions", []),
            "candidate_transactions": candidates_by_incident.get(incident_id, []),
            "replay_status": incident.get("replay_status"),
        }
        splits[split].append(item)
        status_counts[incident.get("replay_status", "unknown")] += 1
        chain_counts[incident["chain"]] += 1
        attack_counts[incident["attack_type"]] += 1
        if not incident.get("key_transactions") and incident_id not in candidates_by_incident:
            missing_key_tx.append(incident_id)

    unlabeled = provider_unlabeled_graphs(root / args.graph_input)
    out_dir = root / args.out_dir
    for split_name, items in splits.items():
        write_json(
            out_dir / "splits" / f"{split_name}.v1.json",
            {
                "schema_ver": "training-split.v1",
                "snapshot_id": split_policy["snapshot_id"],
                "split": split_name,
                "created_at": now_iso(),
                "items": items,
            },
        )
    write_json(
        out_dir / "unlabeled_pool.provider_only.v1.json",
        {
            "schema_ver": "unlabeled-pool.v1",
            "snapshot_id": split_policy["snapshot_id"],
            "created_at": now_iso(),
            "items": unlabeled,
        },
    )
    label_snapshot = {
        "schema_ver": "label-snapshot.v1",
        "snapshot_id": split_policy["snapshot_id"],
        "created_at": now_iso(),
        "positive_incidents": len(incidents),
        "unlabeled_provider_only_graphs": len(unlabeled),
        "split_counts": {name: len(items) for name, items in splits.items()},
        "replay_status_counts": dict(sorted(status_counts.items())),
        "chain_counts": dict(sorted(chain_counts.items())),
        "attack_type_counts": dict(sorted(attack_counts.items())),
        "missing_key_transaction_incidents": sorted(missing_key_tx),
        "candidate_transaction_incidents": sorted(candidates_by_incident),
        "candidate_transactions": sum(len(values) for values in candidates_by_incident.values()),
        "training_ready": False,
        "blocking_reasons": [
            "positive labels are incident-level and not fully mapped to graph replay records",
            "negative samples require rich trace graphs and stratified sampling",
            "candidate transaction hashes require trace replay and analyst promotion",
        ],
    }
    write_json(out_dir / "label_snapshot.v1.json", label_snapshot)

    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "positive_incidents": len(incidents),
        "unlabeled_provider_only_graphs": len(unlabeled),
        "split_counts": label_snapshot["split_counts"],
        "replay_status_counts": label_snapshot["replay_status_counts"],
        "missing_key_transaction_incidents": label_snapshot["missing_key_transaction_incidents"],
        "candidate_transaction_incidents": label_snapshot["candidate_transaction_incidents"],
        "candidate_transactions": label_snapshot["candidate_transactions"],
        "training_ready": False,
        "outputs": [
            "data/training/label_snapshot.v1.json",
            "data/training/splits/train.v1.json",
            "data/training/splits/validation.v1.json",
            "data/training/splits/replay.v1.json",
            "data/training/unlabeled_pool.provider_only.v1.json",
        ],
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
