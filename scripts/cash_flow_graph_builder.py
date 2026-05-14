#!/usr/bin/env python3
"""Build GraphInferenceRequest records from parsed trace features."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FEATURE_VER = "cash-flow-graph-builder.v1"


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


def normalize_address(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    text = "0x" + value[2:].lower()
    if len(text) == 42:
        return text
    if len(text) == 66:
        return "0x" + text[-40:]
    return None


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def stable_id(prefix: str, *parts: Any) -> str:
    seed = ":".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(seed).hexdigest()[:24]}"


def event_id_for(tx_hash: str) -> str:
    return hashlib.sha256(f"graph-inference.v1:{tx_hash}".encode("utf-8")).hexdigest()


def node_address(address: str) -> dict[str, Any]:
    return {
        "node_id": f"address:{address}",
        "node_type": "address",
        "address": address,
    }


def node_asset(token: str, transfer: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": f"asset:{token}",
        "node_type": "asset",
        "address": token,
        "symbol": transfer.get("symbol"),
        "decimals": transfer.get("decimals"),
        "standard": transfer.get("standard"),
    }


def node_protocol(annotation: dict[str, Any]) -> dict[str, Any]:
    address = annotation["address"]
    return {
        "node_id": f"protocol:{address}",
        "node_type": "protocol",
        "address": address,
        "protocol_id": annotation.get("protocol_id"),
        "category": annotation.get("category"),
        "contract": annotation.get("contract"),
        "roles": annotation.get("roles", []),
        "emergency_surface": annotation.get("emergency_surface", False),
    }


def add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> None:
    nodes[node["node_id"]] = node


def build_transfer_edge(transfer: dict[str, Any], ordinal: int) -> dict[str, Any] | None:
    sender = normalize_address(transfer.get("from"))
    receiver = normalize_address(transfer.get("to"))
    token = normalize_address(transfer.get("token"))
    if sender is None or receiver is None:
        return None
    return {
        "edge_id": stable_id("edge", "transfer", transfer.get("event_id"), ordinal),
        "edge_type": "transfer",
        "from_node": f"address:{sender}",
        "to_node": f"address:{receiver}",
        "asset_node": f"asset:{token}" if token else None,
        "standard": transfer.get("standard"),
        "amount_raw": transfer.get("amount_raw"),
        "amount_norm": transfer.get("amount_norm"),
        "token_id": transfer.get("token_id"),
        "log_index": transfer.get("log_index"),
    }


def build_call_edge(call: dict[str, Any], ordinal: int) -> dict[str, Any] | None:
    sender = normalize_address(call.get("from"))
    receiver = normalize_address(call.get("to"))
    if sender is None or receiver is None:
        return None
    return {
        "edge_id": stable_id("edge", "call", ordinal, sender, receiver),
        "edge_type": "call",
        "from_node": f"address:{sender}",
        "to_node": f"address:{receiver}",
        "depth": call.get("depth"),
        "call_type": call.get("type"),
        "function_selector": call.get("function_selector"),
        "function_signature": call.get("function_signature"),
        "function_name": call.get("function_name"),
        "success": call.get("success"),
        "revert_reason": call.get("revert_reason"),
        "value": call.get("value"),
    }


def build_context_edge(annotation: dict[str, Any], side: str, ordinal: int) -> dict[str, Any]:
    address = annotation["address"]
    return {
        "edge_id": stable_id("edge", "context", address, side, ordinal),
        "edge_type": "context",
        "from_node": f"address:{address}",
        "to_node": f"protocol:{address}",
        "context_type": "protocol_role",
        "side": side,
        "roles": annotation.get("roles", []),
    }


def load_protocol_features(root: Path) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        data = read_json(path)
        key = data.get("source_parsed_idempotency_key")
        if isinstance(key, str) and key not in features:
            features[key] = data
    return features


def load_context_file(path: Path | None, timeout_ms: int) -> tuple[dict[str, Any], bool]:
    if path is None:
        return {}, False
    started = time.perf_counter()
    data = read_json(path)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms > timeout_ms:
        return {}, True
    return data if isinstance(data, dict) else {}, False


def build_graph(
    parsed: dict[str, Any],
    protocol_features: dict[str, Any] | None,
    address_context: dict[str, Any] | None = None,
    protocol_context: dict[str, Any] | None = None,
    context_timeout_flags: list[str] | None = None,
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    tx_hash = parsed["tx_hash"]
    add_node(
        nodes,
        {
            "node_id": f"tx:{tx_hash}",
            "node_type": "transaction",
            "tx_hash": tx_hash,
            "trace_source": parsed.get("trace_source"),
            "trace_status": parsed.get("trace_status"),
        },
    )

    for transfer_index, transfer in enumerate(parsed.get("token_transfers", [])):
        if not isinstance(transfer, dict):
            continue
        for side in ("from", "to", "operator"):
            address = normalize_address(transfer.get(side))
            if address is not None:
                add_node(nodes, node_address(address))
        token = normalize_address(transfer.get("token"))
        if token is not None:
            add_node(nodes, node_asset(token, transfer))
        edge = build_transfer_edge(transfer, transfer_index)
        if edge is not None:
            edges.append(edge)

    for call_index, call in enumerate(parsed.get("calls", [])):
        if not isinstance(call, dict):
            continue
        for side in ("from", "to"):
            address = normalize_address(call.get(side))
            if address is not None:
                add_node(nodes, node_address(address))
        edge = build_call_edge(call, call_index)
        if edge is not None:
            edges.append(edge)

    protocol_features = protocol_features or {}
    annotations: list[dict[str, Any]] = []
    for key in (
        "matched_protocol_roles",
        "call_protocol_annotations",
        "transfer_protocol_annotations",
    ):
        value = protocol_features.get(key)
        if isinstance(value, list):
            annotations.extend(item for item in value if isinstance(item, dict))
    seen_protocol_addresses: set[str] = set()
    for idx, annotation in enumerate(annotations):
        address = normalize_address(annotation.get("address"))
        if address is None:
            continue
        annotation = {**annotation, "address": address}
        add_node(nodes, node_address(address))
        if address not in seen_protocol_addresses:
            add_node(nodes, node_protocol(annotation))
            seen_protocol_addresses.add(address)
        edges.append(build_context_edge(annotation, annotation.get("side", "matched"), idx))

    context_windows = ["tx-only"]
    missing_flags = set(parsed.get("feature_missing_flags", []))
    missing_flags.update(protocol_features.get("feature_missing_flags", []))
    if address_context:
        context_windows.append("5m-address")
    else:
        missing_flags.add("context_5m_address_unavailable")
    if protocol_context:
        context_windows.append("1h-protocol")
    else:
        missing_flags.add("context_1h_protocol_unavailable")
    for flag in context_timeout_flags or []:
        missing_flags.add(flag)

    event_id = event_id_for(tx_hash)
    return {
        "event_id": event_id,
        "schema_ver": "graph-inference.v1",
        "chain_id": parsed["chain_id"],
        "created_at": now_iso(),
        "idempotency_key": f"{parsed['idempotency_key']}:graph-inference.v1",
        "graph_id": f"graph:{tx_hash}",
        "tx_hash": tx_hash,
        "nodes": sorted(nodes.values(), key=lambda node: node["node_id"]),
        "edges": edges,
        "feature_ver": FEATURE_VER,
        "context_windows": context_windows,
        "feature_missing_flags": sorted(missing_flags),
        "graph_snapshot_ref": None,
    }


def replay_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "replay"
        / "graph-inference.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def snapshot_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "graph-snapshots"
        / "graph-inference.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def validate_graph_shape(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
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
    missing = sorted(required - set(graph))
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
        errors.append("context_windows must include tx-only")
    return errors


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cash-flow graph inference records.")
    parser.add_argument("--parsed-input", default="data/replay/parsed-trace.v1")
    parser.add_argument("--protocol-features", default="data/replay/protocol-features.v1")
    parser.add_argument("--address-context")
    parser.add_argument("--protocol-context")
    parser.add_argument("--context-timeout-ms", type=int, default=100)
    parser.add_argument("--out", default="ops/reports/cash-flow-graph-builder.latest.json")
    parser.add_argument("--write-replay", action="store_true")
    parser.add_argument("--write-snapshot", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    protocol_feature_index = load_protocol_features(root / args.protocol_features)
    address_context, address_timeout = load_context_file(
        root / args.address_context if args.address_context else None,
        args.context_timeout_ms,
    )
    protocol_context, protocol_timeout = load_context_file(
        root / args.protocol_context if args.protocol_context else None,
        args.context_timeout_ms,
    )
    context_timeout_flags: list[str] = []
    if address_timeout:
        context_timeout_flags.append("context_5m_address_timeout")
    if protocol_timeout:
        context_timeout_flags.append("context_1h_protocol_timeout")

    seen_input_keys: set[str] = set()
    skipped_duplicates = 0
    graphs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    build_latencies_ms: list[float] = []
    node_counts = Counter()
    edge_counts = Counter()
    context_counts = Counter()
    missing_flags = Counter()

    for path in iter_json_files(root / args.parsed_input):
        try:
            parsed = read_json(path)
            key = parsed.get("idempotency_key")
            if not isinstance(key, str):
                errors.append({"path": str(path), "error": "missing idempotency_key"})
                continue
            if key in seen_input_keys:
                skipped_duplicates += 1
                continue
            seen_input_keys.add(key)
            started = time.perf_counter()
            graph = build_graph(
                parsed,
                protocol_feature_index.get(key),
                address_context,
                protocol_context,
                context_timeout_flags,
            )
            build_latencies_ms.append((time.perf_counter() - started) * 1000)
            graph_errors = validate_graph_shape(graph)
            if graph_errors:
                errors.append({"path": str(path), "error": "; ".join(graph_errors)})
                continue
            if args.write_snapshot:
                snapshot_path = snapshot_output_path(root, graph)
                graph["graph_snapshot_ref"] = str(snapshot_path.relative_to(root))
                write_json(snapshot_path, graph)
            if args.write_replay:
                write_json(replay_output_path(root, graph), graph)
            graphs.append(graph)
            for node in graph["nodes"]:
                node_counts[node.get("node_type", "unknown")] += 1
            for edge in graph["edges"]:
                edge_counts[edge.get("edge_type", "unknown")] += 1
            for window in graph["context_windows"]:
                context_counts[window] += 1
            for flag in graph["feature_missing_flags"]:
                missing_flags[flag] += 1
        except Exception as exc:  # noqa: BLE001 - report all build errors.
            errors.append({"path": str(path), "error": str(exc)})

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "parsed_input": args.parsed_input,
        "protocol_features": args.protocol_features,
        "files_seen": len(iter_json_files(root / args.parsed_input)),
        "unique_parsed_records": len(seen_input_keys),
        "skipped_duplicate_parsed_records": skipped_duplicates,
        "graphs_built": len(graphs),
        "write_replay": args.write_replay,
        "write_snapshot": args.write_snapshot,
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "context_window_counts": dict(sorted(context_counts.items())),
        "feature_missing_flags": dict(sorted(missing_flags.items())),
        "build_latency_ms": {
            "p50": percentile(build_latencies_ms, 50),
            "p95": percentile(build_latencies_ms, 95),
            "max": round(max(build_latencies_ms), 3) if build_latencies_ms else None,
        },
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
