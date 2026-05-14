#!/usr/bin/env python3
"""Validate graph-inference replay files after graph builder runs."""

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
    "graph_id",
    "tx_hash",
    "nodes",
    "edges",
    "feature_ver",
    "context_windows",
    "feature_missing_flags",
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


def validate_graph(root: Path, path: Path, graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(graph))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if graph.get("schema_ver") != "graph-inference.v1":
        errors.append("schema_ver mismatch")
    if graph.get("chain_id") != 1:
        errors.append("chain_id must be 1")
    if not isinstance(graph.get("nodes"), list):
        errors.append("nodes must be list")
    if not isinstance(graph.get("edges"), list):
        errors.append("edges must be list")
    if "tx-only" not in graph.get("context_windows", []):
        errors.append("context_windows missing tx-only")
    if not isinstance(graph.get("feature_missing_flags"), list):
        errors.append("feature_missing_flags must be list")
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or not node.get("node_id") or not node.get("node_type"):
            errors.append("node missing node_id or node_type")
            break
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict) or not edge.get("edge_id") or not edge.get("edge_type"):
            errors.append("edge missing edge_id or edge_type")
            break
    snapshot_ref = graph.get("graph_snapshot_ref")
    if snapshot_ref is not None:
        snapshot_path = root / snapshot_ref
        if not snapshot_path.exists():
            errors.append(f"missing graph_snapshot_ref target: {snapshot_ref}")
    if path.name != f"{graph.get('event_id')}.json":
        errors.append("file name does not match event_id")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate graph-inference replay files.")
    parser.add_argument("--input", default="data/replay/graph-inference.v1")
    parser.add_argument("--out", default="ops/reports/graph-replay-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    input_path = root / args.input
    files = iter_json_files(input_path)
    errors: list[dict[str, Any]] = []
    idempotency_counts = Counter()
    node_counts = Counter()
    edge_counts = Counter()
    context_counts = Counter()
    missing_flags = Counter()
    valid_graphs = 0

    for path in files:
        try:
            graph = read_json(path)
            graph_errors = validate_graph(root, path, graph)
            if graph_errors:
                errors.append({"path": str(path), "errors": graph_errors})
                continue
            valid_graphs += 1
            idempotency_counts[graph["idempotency_key"]] += 1
            for node in graph["nodes"]:
                node_counts[node.get("node_type", "unknown")] += 1
            for edge in graph["edges"]:
                edge_counts[edge.get("edge_type", "unknown")] += 1
            for window in graph["context_windows"]:
                context_counts[window] += 1
            for flag in graph["feature_missing_flags"]:
                missing_flags[flag] += 1
        except Exception as exc:  # noqa: BLE001 - keep scanning.
            errors.append({"path": str(path), "errors": [str(exc)]})

    duplicate_keys = sorted(key for key, count in idempotency_counts.items() if count > 1)
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors and not duplicate_keys else "failed",
        "input": args.input,
        "files_seen": len(files),
        "valid_graphs": valid_graphs,
        "unique_idempotency_keys": len(idempotency_counts),
        "duplicate_idempotency_keys": duplicate_keys,
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "context_window_counts": dict(sorted(context_counts.items())),
        "feature_missing_flags": dict(sorted(missing_flags.items())),
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
