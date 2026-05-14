#!/usr/bin/env python3
"""Quality checks for graph-inference replay records."""

from __future__ import annotations

import argparse
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


def check_node(node: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    node_id = node.get("node_id")
    node_type = node.get("node_type")
    if not isinstance(node_id, str) or not isinstance(node_type, str):
        return ["node missing node_id or node_type"]
    expected_prefix = {
        "transaction": "tx:",
        "address": "address:0x",
        "asset": "asset:0x",
        "protocol": "protocol:0x",
    }.get(node_type)
    if expected_prefix is None:
        errors.append(f"unknown node_type {node_type}")
    elif not node_id.startswith(expected_prefix):
        errors.append(f"{node_type} node id has wrong prefix: {node_id}")
    return errors


def check_edge(edge: dict[str, Any], nodes: set[str]) -> list[str]:
    errors: list[str] = []
    edge_type = edge.get("edge_type")
    from_node = edge.get("from_node")
    to_node = edge.get("to_node")
    if edge_type not in {"transfer", "call", "context"}:
        errors.append(f"unknown edge_type {edge_type}")
    if from_node not in nodes:
        errors.append(f"from_node not found: {from_node}")
    if to_node not in nodes:
        errors.append(f"to_node not found: {to_node}")
    if edge_type == "transfer":
        if not isinstance(from_node, str) or not from_node.startswith("address:"):
            errors.append("transfer from_node must be address")
        if not isinstance(to_node, str) or not to_node.startswith("address:"):
            errors.append("transfer to_node must be address")
        asset_node = edge.get("asset_node")
        if asset_node is not None and asset_node not in nodes:
            errors.append(f"transfer asset_node not found: {asset_node}")
    if edge_type == "call":
        if not isinstance(from_node, str) or not from_node.startswith("address:"):
            errors.append("call from_node must be address")
        if not isinstance(to_node, str) or not to_node.startswith("address:"):
            errors.append("call to_node must be address")
        depth = edge.get("depth")
        if depth is not None and (not isinstance(depth, int) or depth < 0):
            errors.append("call depth must be non-negative integer or null")
    if edge_type == "context":
        if not isinstance(from_node, str) or not from_node.startswith("address:"):
            errors.append("context from_node must be address")
        if not isinstance(to_node, str) or not to_node.startswith("protocol:"):
            errors.append("context to_node must be protocol")
    return errors


def check_graph(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    node_ids = {node.get("node_id") for node in nodes if isinstance(node, dict)}
    tx_nodes = [node for node in nodes if isinstance(node, dict) and node.get("node_type") == "transaction"]
    if len(tx_nodes) != 1:
        errors.append(f"expected exactly one transaction node, got {len(tx_nodes)}")
    for node in nodes:
        if isinstance(node, dict):
            errors.extend(check_node(node))
        else:
            errors.append("node must be object")
    for edge in edges:
        if isinstance(edge, dict):
            errors.extend(check_edge(edge, node_ids))
        else:
            errors.append("edge must be object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Run quality checks on graph replay files.")
    parser.add_argument("--input", default="data/replay/graph-inference.v1")
    parser.add_argument(
        "--builder-report", default="ops/reports/cash-flow-graph-builder.latest.json"
    )
    parser.add_argument("--out", default="ops/reports/graph-quality-check.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    files = iter_json_files(root / args.input)
    errors: list[dict[str, Any]] = []
    node_counts = Counter()
    edge_counts = Counter()
    graphs_checked = 0

    for path in files:
        try:
            graph = read_json(path)
            graph_errors = check_graph(graph)
            if graph_errors:
                errors.append({"path": str(path), "errors": graph_errors})
                continue
            graphs_checked += 1
            for node in graph.get("nodes", []):
                node_counts[node.get("node_type", "unknown")] += 1
            for edge in graph.get("edges", []):
                edge_counts[edge.get("edge_type", "unknown")] += 1
        except Exception as exc:  # noqa: BLE001 - audit should keep scanning.
            errors.append({"path": str(path), "errors": [str(exc)]})

    latency_report: dict[str, Any] = {}
    builder_report_path = root / args.builder_report
    if builder_report_path.exists():
        builder_report = read_json(builder_report_path)
        latency_report = builder_report.get("build_latency_ms", {})

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "input": args.input,
        "files_seen": len(files),
        "graphs_checked": graphs_checked,
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "build_latency_ms": latency_report,
        "coverage_notes": [
            "Current provider-only graphs contain no transfer/call/context edges.",
            "Edge direction, call depth, and protocol role checks are enforced when such edges exist.",
        ],
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
