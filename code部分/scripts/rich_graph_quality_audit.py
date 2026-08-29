#!/usr/bin/env python3
"""Strict lineage and structural gate for paid historical rich graphs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_TRACE_SOURCE = "trace_transaction"
EXPECTED_PARSER_VER = "trace-parser.v1"
EXPECTED_ENRICHER_VER = "protocol-role-enricher.v1"
EXPECTED_GRAPH_VER = "cash-flow-graph-builder.v1"


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


def iter_json_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.json"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record_index(path: Path) -> tuple[dict[str, list[tuple[Path, dict[str, Any]]]], list[str]]:
    index: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    read_errors: list[str] = []
    for item_path in iter_json_files(path):
        try:
            payload = read_json(item_path)
            tx_hash = payload.get("tx_hash") if isinstance(payload, dict) else None
            if not isinstance(tx_hash, str):
                read_errors.append(f"{item_path}: missing tx_hash")
                continue
            index[tx_hash.lower()].append((item_path, payload))
        except Exception as exc:  # noqa: BLE001 - retain every audit failure.
            read_errors.append(f"{item_path}: {exc}")
    return dict(index), read_errors


def queue_items(path: Path, cohort: str) -> list[dict[str, Any]]:
    payload = read_json(path)
    return [{**item, "audit_cohort": cohort} for item in payload.get("items", [])]


def stratified_normal_review(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_bucket[str(item.get("selection_bucket") or "unknown")].append(item)
    selected: list[dict[str, Any]] = []
    buckets = sorted(by_bucket)
    while len(selected) < count and any(by_bucket.values()):
        for bucket in buckets:
            if by_bucket[bucket] and len(selected) < count:
                selected.append(by_bucket[bucket].pop(0))
    return selected


def one_record(
    index: dict[str, list[tuple[Path, dict[str, Any]]]],
    tx_hash: str,
) -> tuple[Path, dict[str, Any]] | None:
    records = index.get(tx_hash.lower(), [])
    return records[0] if len(records) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict audit for 57 paid rich graphs.")
    parser.add_argument("--exploit-queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--normal-queue", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--raw-manifest", default="data/training/raw-trace-manifest.stage2.v1.json")
    parser.add_argument("--trace-input", default="data/replay/trace-bundle.v1/dt=2026-08-29")
    parser.add_argument("--parsed-input", default="data/replay/parsed-trace.v1/dt=2026-08-29")
    parser.add_argument("--protocol-input", default="data/replay/protocol-features.v1/dt=2026-08-29")
    parser.add_argument("--graph-input", default="data/replay/graph-inference.v1/dt=2026-08-29")
    parser.add_argument("--expected-exploit", type=int, default=7)
    parser.add_argument("--expected-normal", type=int, default=50)
    parser.add_argument("--normal-review-count", type=int, default=10)
    parser.add_argument("--out", default="ops/reports/rich-graph-quality-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    exploit_items = queue_items(root / args.exploit_queue, "exploit_candidate")
    normal_items = queue_items(root / args.normal_queue, "normal_candidate")
    all_items = exploit_items + normal_items
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors_by_tx: Counter[str] = Counter()

    def error(layer: str, message: str, tx_hash: str | None = None) -> None:
        errors.append({"layer": layer, "tx_hash": tx_hash, "message": message})
        if tx_hash:
            errors_by_tx[tx_hash.lower()] += 1

    if len(exploit_items) != args.expected_exploit:
        error("queue", f"exploit count {len(exploit_items)} != {args.expected_exploit}")
    if len(normal_items) != args.expected_normal:
        error("queue", f"normal count {len(normal_items)} != {args.expected_normal}")

    expected: dict[str, dict[str, Any]] = {}
    for item in all_items:
        tx_hash = item.get("tx_hash")
        if not isinstance(tx_hash, str):
            error("queue", "queue item missing tx_hash")
            continue
        key = tx_hash.lower()
        if key in expected:
            error("queue", "duplicate or cross-cohort tx_hash", key)
        expected[key] = item
    expected_hashes = set(expected)

    indexes: dict[str, dict[str, list[tuple[Path, dict[str, Any]]]]] = {}
    for layer, relative in {
        "trace_bundle": args.trace_input,
        "parsed_trace": args.parsed_input,
        "protocol_features": args.protocol_input,
        "graph": args.graph_input,
    }.items():
        index, read_errors = record_index(root / relative)
        indexes[layer] = index
        for message in read_errors:
            error(layer, message)
        for tx_hash, records in index.items():
            if tx_hash not in expected_hashes:
                error(layer, "record is outside the frozen 57-transaction queue", tx_hash)
            if len(records) != 1:
                error(layer, f"expected one record, found {len(records)}", tx_hash)
        for tx_hash in sorted(expected_hashes - set(index)):
            error(layer, "missing record", tx_hash)

    raw_manifest = read_json(root / args.raw_manifest)
    raw_entries = {
        str(item.get("tx_hash", "")).lower(): item
        for item in raw_manifest.get("entries", [])
        if isinstance(item, dict)
    }
    if set(raw_entries) != expected_hashes:
        error("raw_manifest", "manifest tx_hash set does not match frozen queues")

    node_counts = Counter()
    edge_counts = Counter()
    missing_flags = Counter()
    cohort_stats: dict[str, Counter[str]] = defaultdict(Counter)
    max_call_depth = 0
    raw_bytes = 0
    graph_bytes = 0
    reviewed_summaries: dict[str, dict[str, Any]] = {}

    for tx_hash, queue_item in sorted(expected.items()):
        cohort = str(queue_item["audit_cohort"])
        trace_item = one_record(indexes["trace_bundle"], tx_hash)
        parsed_item = one_record(indexes["parsed_trace"], tx_hash)
        protocol_item = one_record(indexes["protocol_features"], tx_hash)
        graph_item = one_record(indexes["graph"], tx_hash)
        if not all((trace_item, parsed_item, protocol_item, graph_item)):
            continue
        trace_path, trace = trace_item
        parsed_path, parsed = parsed_item
        protocol_path, protocol = protocol_item
        graph_path, graph = graph_item

        if trace.get("chain_id") != 1:
            error("trace_bundle", "chain_id is not Ethereum Mainnet", tx_hash)
        if trace.get("trace_source") != EXPECTED_TRACE_SOURCE:
            error("trace_bundle", f"trace_source is {trace.get('trace_source')!r}", tx_hash)
        if trace.get("trace_status") != "ok":
            error("trace_bundle", f"trace_status is {trace.get('trace_status')!r}", tx_hash)
        if not isinstance(trace.get("calls"), list) or not trace["calls"]:
            error("trace_bundle", "empty call trace", tx_hash)

        manifest_entry = raw_entries.get(tx_hash)
        raw_ref = trace.get("raw_trace_ref")
        if not isinstance(raw_ref, str) or not raw_ref:
            error("trace_bundle", "raw_trace_ref is missing", tx_hash)
        else:
            raw_path = root / raw_ref
            if not raw_path.exists():
                error("trace_bundle", f"raw trace target does not exist: {raw_ref}", tx_hash)
            else:
                raw_bytes += raw_path.stat().st_size
                if manifest_entry and sha256_file(raw_path) != manifest_entry.get("raw_sha256"):
                    error("raw_manifest", "raw trace SHA-256 mismatch", tx_hash)
        if manifest_entry and manifest_entry.get("bundle_ref") != str(trace_path.relative_to(root)):
            error("raw_manifest", "bundle_ref does not resolve to audited bundle", tx_hash)

        if parsed.get("source_trace_event_id") != trace.get("event_id"):
            error("parsed_trace", "source trace event lineage mismatch", tx_hash)
        if parsed.get("source_trace_idempotency_key") != trace.get("idempotency_key"):
            error("parsed_trace", "source trace idempotency lineage mismatch", tx_hash)
        if parsed.get("raw_trace_ref") != raw_ref:
            error("parsed_trace", "raw trace lineage mismatch", tx_hash)
        if parsed.get("parser_ver") != EXPECTED_PARSER_VER:
            error("parsed_trace", f"unexpected parser_ver {parsed.get('parser_ver')!r}", tx_hash)
        if parsed.get("trace_source") != EXPECTED_TRACE_SOURCE or parsed.get("trace_status") != "ok":
            error("parsed_trace", "non-rich or unsuccessful parsed trace", tx_hash)
        if len(parsed.get("calls", [])) != len(trace.get("calls", [])):
            error("parsed_trace", "parsed call count differs from trace bundle", tx_hash)

        if protocol.get("source_parsed_event_id") != parsed.get("event_id"):
            error("protocol_features", "source parsed event lineage mismatch", tx_hash)
        if protocol.get("source_parsed_idempotency_key") != parsed.get("idempotency_key"):
            error("protocol_features", "source parsed idempotency lineage mismatch", tx_hash)
        if protocol.get("feature_enricher_ver") != EXPECTED_ENRICHER_VER:
            error("protocol_features", "unexpected protocol role enricher version", tx_hash)

        if graph.get("chain_id") != 1 or graph.get("tx_hash", "").lower() != tx_hash:
            error("graph", "transaction identity mismatch", tx_hash)
        if graph.get("feature_ver") != EXPECTED_GRAPH_VER:
            error("graph", f"unexpected feature_ver {graph.get('feature_ver')!r}", tx_hash)
        if EXPECTED_TRACE_SOURCE not in str(graph.get("idempotency_key", "")):
            error("graph", "idempotency key does not prove trace_transaction lineage", tx_hash)

        lineage = graph.get("lineage") if isinstance(graph.get("lineage"), dict) else {}
        expected_lineage = {
            "transaction_ref": f"ethereum:1:{tx_hash}",
            "trace_bundle_event_id": trace.get("event_id"),
            "trace_bundle_idempotency_key": trace.get("idempotency_key"),
            "raw_trace_ref": raw_ref,
            "parsed_trace_event_id": parsed.get("event_id"),
            "parsed_trace_idempotency_key": parsed.get("idempotency_key"),
            "protocol_features_event_id": protocol.get("event_id"),
            "protocol_features_idempotency_key": protocol.get("idempotency_key"),
            "trace_parser_ver": EXPECTED_PARSER_VER,
            "protocol_role_enricher_ver": EXPECTED_ENRICHER_VER,
            "graph_builder_ver": EXPECTED_GRAPH_VER,
        }
        for key, value in expected_lineage.items():
            if lineage.get(key) != value:
                error("graph", f"lineage mismatch for {key}", tx_hash)

        snapshot_ref = graph.get("graph_snapshot_ref")
        if not isinstance(snapshot_ref, str):
            error("graph", "graph_snapshot_ref is missing", tx_hash)
        else:
            snapshot_path = root / snapshot_ref
            if not snapshot_path.exists():
                error("graph", f"snapshot target does not exist: {snapshot_ref}", tx_hash)
            elif sha256_file(snapshot_path) != sha256_file(graph_path):
                error("graph", "snapshot and replay graph differ", tx_hash)
        graph_bytes += graph_path.stat().st_size

        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
        node_ids = [node.get("node_id") for node in nodes if isinstance(node, dict)]
        edge_ids = [edge.get("edge_id") for edge in edges if isinstance(edge, dict)]
        if len(node_ids) != len(set(node_ids)):
            error("graph", "duplicate node IDs", tx_hash)
        if len(edge_ids) != len(set(edge_ids)):
            error("graph", "duplicate edge IDs", tx_hash)
        tx_nodes = [node for node in nodes if node.get("node_type") == "transaction"]
        if len(tx_nodes) != 1 or tx_nodes[0].get("tx_hash", "").lower() != tx_hash:
            error("graph", "expected one matching transaction node", tx_hash)

        node_id_set = set(node_ids)
        call_edges = [edge for edge in edges if edge.get("edge_type") == "call"]
        transfer_edges = [edge for edge in edges if edge.get("edge_type") == "transfer"]
        if not call_edges:
            error("graph", "missing key Call edge", tx_hash)
        if len(call_edges) != len(parsed.get("calls", [])):
            error("graph", "Call edge count differs from parsed calls", tx_hash)
        if len(transfer_edges) != len(parsed.get("token_transfers", [])):
            error("graph", "Transfer edge count differs from parsed transfers", tx_hash)
        for edge in edges:
            if edge.get("from_node") not in node_id_set or edge.get("to_node") not in node_id_set:
                error("graph", f"edge {edge.get('edge_id')} has dangling endpoint", tx_hash)
        for edge in call_edges:
            depth = edge.get("call_depth")
            if not isinstance(depth, int) or depth < 0:
                error("graph", f"Call edge {edge.get('edge_id')} has invalid depth", tx_hash)
            else:
                max_call_depth = max(max_call_depth, depth)
            for field in ("call_type", "semantic_action", "success", "value"):
                if edge.get(field) is None:
                    error("graph", f"Call edge {edge.get('edge_id')} missing {field}", tx_hash)
        for edge in transfer_edges:
            if not isinstance(edge.get("amount_raw"), str):
                error("graph", f"Transfer edge {edge.get('edge_id')} missing raw amount", tx_hash)
            asset_node = edge.get("asset_node")
            if not isinstance(asset_node, str) or asset_node not in node_id_set:
                error("graph", f"Transfer edge {edge.get('edge_id')} missing asset node", tx_hash)
            if edge.get("amount_norm") is None and "token_decimals_missing" not in graph.get("feature_missing_flags", []):
                error("graph", f"Transfer edge {edge.get('edge_id')} has unexplained normalized amount", tx_hash)

        role_addresses = {
            str(item.get("address", "")).lower()
            for item in protocol.get("matched_protocol_roles", [])
            if isinstance(item, dict)
        }
        protocol_addresses = {
            str(node.get("address", "")).lower()
            for node in nodes
            if isinstance(node, dict) and node.get("node_type") == "protocol"
        }
        if role_addresses != protocol_addresses:
            error("graph", "protocol role nodes do not match enriched roles", tx_hash)

        for flag in graph.get("feature_missing_flags", []):
            missing_flags[str(flag)] += 1
            if str(flag).startswith("trace_"):
                error("graph", f"forbidden trace quality flag {flag}", tx_hash)
        for node in nodes:
            node_counts[str(node.get("node_type", "unknown"))] += 1
        for edge in edges:
            edge_counts[str(edge.get("edge_type", "unknown"))] += 1
        cohort_stats[cohort]["graphs"] += 1
        cohort_stats[cohort]["calls"] += len(call_edges)
        cohort_stats[cohort]["transfers"] += len(transfer_edges)
        if "5m-address" in graph.get("context_windows", []):
            cohort_stats[cohort]["address_context_graphs"] += 1
        if role_addresses:
            cohort_stats[cohort]["protocol_role_graphs"] += 1

        reviewed_summaries[tx_hash] = {
            "tx_hash": tx_hash,
            "cohort": cohort,
            "incident_id": queue_item.get("incident_id"),
            "selection_bucket": queue_item.get("selection_bucket"),
            "trace_bundle_ref": str(trace_path.relative_to(root)),
            "parsed_trace_ref": str(parsed_path.relative_to(root)),
            "protocol_features_ref": str(protocol_path.relative_to(root)),
            "graph_ref": str(graph_path.relative_to(root)),
            "nodes": len(nodes),
            "call_edges": len(call_edges),
            "transfer_edges": len(transfer_edges),
            "context_edges": sum(edge.get("edge_type") == "context" for edge in edges),
            "max_call_depth": max((edge.get("call_depth", 0) for edge in call_edges), default=0),
            "protocol_roles": sorted(role_addresses),
            "feature_missing_flags": graph.get("feature_missing_flags", []),
        }

    review_items = exploit_items + stratified_normal_review(normal_items, args.normal_review_count)
    review = []
    for item in review_items:
        tx_hash = str(item.get("tx_hash", "")).lower()
        summary = reviewed_summaries.get(tx_hash, {"tx_hash": tx_hash})
        review.append(
            {
                **summary,
                "review_kind": "agent_assisted_structural_review",
                "review_status": "passed" if errors_by_tx[tx_hash] == 0 else "failed",
            }
        )

    context_rates = {}
    for cohort in ("exploit_candidate", "normal_candidate"):
        stats = cohort_stats[cohort]
        graphs = stats["graphs"]
        context_rates[cohort] = round(stats["address_context_graphs"] / graphs, 4) if graphs else 0.0
    context_gap = abs(context_rates["exploit_candidate"] - context_rates["normal_candidate"])
    if context_gap > 0.25:
        warnings.append(
            {
                "code": "context_cohort_coverage_skew",
                "message": "5m address-context coverage differs by more than 25 percentage points; keep context ablation and leakage checks mandatory.",
                "rates": context_rates,
            }
        )
    graphs_with_roles = sum(stats["protocol_role_graphs"] for stats in cohort_stats.values())
    if expected_hashes and graphs_with_roles / len(expected_hashes) < 0.25:
        warnings.append(
            {
                "code": "protocol_role_coverage_low",
                "message": "Configured protocol-role dictionary covers fewer than 25% of rich graphs; expand it before research-grade training.",
                "graphs_with_roles": graphs_with_roles,
            }
        )

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "gate": "phase3_rich_graph_quality",
        "training_scope": "engineering_smoke_only_pending_label_promotion",
        "inputs": {
            "exploit_queue": args.exploit_queue,
            "normal_queue": args.normal_queue,
            "raw_manifest": args.raw_manifest,
            "trace_input": args.trace_input,
            "parsed_input": args.parsed_input,
            "protocol_input": args.protocol_input,
            "graph_input": args.graph_input,
        },
        "expected": {
            "exploit_graphs": args.expected_exploit,
            "normal_graphs": args.expected_normal,
            "total_graphs": args.expected_exploit + args.expected_normal,
        },
        "audited": {
            "unique_transactions": len(expected_hashes),
            "trace_bundles": len(indexes.get("trace_bundle", {})),
            "parsed_traces": len(indexes.get("parsed_trace", {})),
            "protocol_feature_records": len(indexes.get("protocol_features", {})),
            "graphs": len(indexes.get("graph", {})),
            "raw_trace_bytes": raw_bytes,
            "graph_replay_bytes": graph_bytes,
        },
        "versions": {
            "trace_parser": EXPECTED_PARSER_VER,
            "protocol_role_enricher": EXPECTED_ENRICHER_VER,
            "graph_builder_and_feature_contract": EXPECTED_GRAPH_VER,
        },
        "node_counts": dict(sorted(node_counts.items())),
        "edge_counts": dict(sorted(edge_counts.items())),
        "max_call_depth": max_call_depth,
        "feature_missing_flags": dict(sorted(missing_flags.items())),
        "cohort_stats": {
            key: dict(sorted(value.items())) for key, value in sorted(cohort_stats.items())
        },
        "context_address_coverage_rates": context_rates,
        "structural_review": {
            "method": "all exploit graphs plus a deterministic bucket-stratified normal sample",
            "exploit_reviewed": len(exploit_items),
            "normal_reviewed": len(review) - len(exploit_items),
            "items": review,
        },
        "warnings": warnings,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
