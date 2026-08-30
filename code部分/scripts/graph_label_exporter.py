#!/usr/bin/env python3
"""Export promoted analyst decisions into graph-level training labels."""

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


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def load_graph_index(root: Path, project_root: Path | None = None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        graph = read_json(path)
        tx_hash = graph.get("tx_hash")
        if isinstance(tx_hash, str):
            key = tx_hash.lower()
            if key in index:
                raise ValueError(f"duplicate graph tx_hash in scoped graph input: {key}")
            graph_path = path
            if project_root is not None:
                try:
                    graph_path = path.resolve().relative_to(project_root.resolve())
                except ValueError:
                    graph_path = path.resolve()
            index[key] = {
                "graph_event_id": graph.get("event_id"),
                "graph_id": graph.get("graph_id"),
                "graph_path": str(graph_path),
                "feature_ver": graph.get("feature_ver"),
                "context_windows": graph.get("context_windows", []),
                "feature_missing_flags": graph.get("feature_missing_flags", []),
            }
    return index


def promoted_items(decisions: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for key in ("exploit_decisions", "normal_decisions"):
        for item in decisions.get(key, []):
            if not isinstance(item, dict):
                continue
            if item.get("decision") == "promoted" and item.get("promotion_status") == "promoted":
                items.append(item)
    return items


def build_label(item: dict[str, Any], graph_index: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    tx_hash = item.get("tx_hash")
    if not isinstance(tx_hash, str):
        return None, "missing_tx_hash"
    graph = graph_index.get(tx_hash.lower())
    graph_ref = item.get("graph_ref")
    if graph is None:
        return None, "graph_not_found"
    if isinstance(graph_ref, str) and graph_ref != graph["graph_path"]:
        return None, "graph_ref_mismatch"
    label = item.get("candidate_label")
    if label not in {0, 1}:
        return None, "invalid_label"
    return {
        "tx_hash": tx_hash.lower(),
        "label": int(label),
        "incident_id": item.get("incident_id"),
        "label_semantics": item.get("label_semantics"),
        "label_scope": item.get("label_scope"),
        "label_version": item.get("label_version"),
        "candidate_role": item.get("candidate_role"),
        "queue_id": item.get("queue_id"),
        "analyst": item.get("analyst"),
        "reviewed_at": item.get("reviewed_at"),
        "trace_bundle_ref": item.get("trace_bundle_ref"),
        "graph_ref": graph_ref or graph["graph_path"],
        "graph_id": graph.get("graph_id"),
        "graph_event_id": graph.get("graph_event_id"),
        "feature_ver": graph.get("feature_ver"),
        "context_windows": graph.get("context_windows", []),
        "feature_missing_flags": graph.get("feature_missing_flags", []),
    }, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Export promoted graph labels for GraphSAGE training.")
    parser.add_argument("--decisions", default="data/training/label_promotion_decisions.stage4.v1.json")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1/dt=2026-08-29")
    parser.add_argument("--out", default="data/training/graph_labels.stage4.v1.json")
    parser.add_argument("--report", default="ops/reports/graph-label-exporter.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    decisions = read_json(root / args.decisions)
    graph_index = load_graph_index(root / args.graphs, root)
    labels = []
    errors = []
    for item in promoted_items(decisions):
        label, error = build_label(item, graph_index)
        if error:
            errors.append({"tx_hash": item.get("tx_hash"), "error": error})
            continue
        assert label is not None
        labels.append(label)
    label_counts = Counter(item["label"] for item in labels)
    training_ready = bool(labels) and set(label_counts) == {0, 1} and not errors
    payload = {
        "schema_ver": "graph-labels.stage4.v1",
        "created_at": now_iso(),
        "snapshot_id": decisions.get("snapshot_id"),
        "label_version": decisions.get("label_version"),
        "feature_version": decisions.get("feature_version"),
        "training_scope": decisions.get("training_scope"),
        "research_training_ready": False,
        "training_ready": training_ready,
        "labels": sorted(labels, key=lambda item: item["tx_hash"]),
        "blocking_reasons": [] if training_ready else [
            reason
            for reason, active in {
                "no_promoted_graph_labels": not labels,
                "positive_and_negative_labels_required": bool(labels) and set(label_counts) != {0, 1},
                "label_export_errors": bool(errors),
            }.items()
            if active
        ],
    }
    payload["label_content_hash"] = canonical_hash(payload["labels"])
    write_json(root / args.out, payload)
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "graphs_seen": len(graph_index),
        "promoted_labels": len(labels),
        "label_counts": {str(key): value for key, value in sorted(label_counts.items())},
        "training_ready": training_ready,
        "research_training_ready": False,
        "label_content_hash": payload["label_content_hash"],
        "out": args.out,
        "errors": errors,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
