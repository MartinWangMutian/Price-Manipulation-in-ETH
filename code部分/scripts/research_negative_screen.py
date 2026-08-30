#!/usr/bin/env python3
"""Screen Stage 8 negative candidates without assigning training labels."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_expansion_builder import canonical_hash, read_json, write_json
from stage4_label_review_builder import (
    ADDRESS_RE,
    exploit_corpus_hashes,
    extract_regex_values,
    graph_stats,
    sha256_file,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def graph_index(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(root.rglob("*.json")):
        payload = read_json(path)
        tx_hash = payload.get("tx_hash")
        if isinstance(tx_hash, str):
            key = tx_hash.lower()
            if key in result:
                raise ValueError(f"duplicate graph for {key}")
            result[key] = (path, payload)
    return result


def endpoint_addresses(queue_item: dict[str, Any], graph: dict[str, Any]) -> set[str]:
    values = {queue_item.get("from"), queue_item.get("to")}
    values.update(
        node.get("address")
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
    )
    return {
        str(value).lower()
        for value in values
        if isinstance(value, str) and ADDRESS_RE.fullmatch(value)
    }


def hard_negative(stats: dict[str, Any], thresholds: dict[str, int]) -> bool:
    return any(
        (
            stats["call_edges"] >= int(thresholds["call_edges_min"]),
            stats["transfer_edges"] >= int(thresholds["transfer_edges_min"]),
            stats["max_call_depth"] >= int(thresholds["max_call_depth_min"]),
        )
    )


def classify(
    queue_item: dict[str, Any],
    graph: dict[str, Any],
    exploit_hashes: set[str],
    sanction_addresses: set[str],
    positive_hashes: set[str],
    thresholds: dict[str, int],
) -> dict[str, Any]:
    tx_hash = str(queue_item["tx_hash"]).lower()
    addresses = endpoint_addresses(queue_item, graph)
    blockers = []
    if tx_hash in exploit_hashes:
        blockers.append("known_exploit_transaction_hash_match")
    sanction_hits = sorted(addresses & sanction_addresses)
    if sanction_hits:
        blockers.append("ofac_sdn_graph_address_match")
    if tx_hash in positive_hashes:
        blockers.append("positive_anchor_overlap")
    stats = graph_stats(graph)
    return {
        "tx_hash": tx_hash,
        "candidate_label": None,
        "review_status": "blocked_unlabeled" if blockers else "screen_pass_human_review_required",
        "human_review_completed": False,
        "hard_negative_candidate": hard_negative(stats, thresholds),
        "graph_stats": stats,
        "known_exploit_transaction_hash_match": tx_hash in exploit_hashes,
        "ofac_sdn_graph_address_hits": sanction_hits,
        "positive_anchor_overlap": tx_hash in positive_hashes,
        "screened_graph_addresses": len(addresses),
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen Stage 8 negative candidates without promotion.")
    parser.add_argument("--config", default="config/research_expansion.stage8.v1.json")
    parser.add_argument("--queue", default="data/training/research_pilot_negative_trace_queue.stage8.v1.json")
    parser.add_argument("--incidents", default="data/training/research_incidents.stage8.v1.json")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1/dt=2026-08-30")
    parser.add_argument("--exploit-corpus", required=True)
    parser.add_argument("--exploit-corpus-version", required=True)
    parser.add_argument("--ofac-sdn", required=True)
    parser.add_argument("--out", default="data/training/research_negative_screen.stage8.pilot.v1.json")
    parser.add_argument("--report", default="ops/reports/research-negative-screen.stage8.pilot.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    config = read_json(root / args.config)
    queue = read_json(root / args.queue)
    incidents = read_json(root / args.incidents)
    graphs = graph_index(root / args.graphs)
    corpus_path = Path(args.exploit_corpus)
    ofac_path = Path(args.ofac_sdn)
    exploit_hashes = exploit_corpus_hashes(corpus_path)
    sanction_addresses = extract_regex_values(ofac_path, ADDRESS_RE)
    positive_hashes = {
        str(value).lower()
        for incident in incidents.get("incidents", [])
        for value in incident.get("anchor_transactions", [])
    }
    thresholds = config["negative_sampling"]["hard_negative_thresholds"]
    errors = []
    decisions = []
    for item in queue.get("items", []):
        tx_hash = str(item.get("tx_hash", "")).lower()
        graph_entry = graphs.get(tx_hash)
        if graph_entry is None:
            errors.append(f"missing graph for {tx_hash}")
            continue
        graph_path, graph = graph_entry
        decision = classify(
            item,
            graph,
            exploit_hashes,
            sanction_addresses,
            positive_hashes,
            thresholds,
        )
        decision["graph_ref"] = str(graph_path.relative_to(root))
        decision["matched_incident_id"] = item.get("matched_incident_id")
        decision["block_number"] = item.get("block_number")
        decision["block_offset"] = item.get("block_offset")
        decisions.append(decision)

    created_at = now_iso()
    payload = {
        "schema_ver": "research-negative-screen.stage8.v1",
        "snapshot_id": queue.get("snapshot_id"),
        "created_at": created_at,
        "candidate_label": None,
        "human_review_completed": False,
        "screening_sources": {
            "known_exploit_corpus": {
                "source": "https://github.com/SunWeb3Sec/DeFiHackLabs",
                "version": args.exploit_corpus_version,
                "transaction_hashes_indexed": len(exploit_hashes),
            },
            "ofac_sdn": {
                "source": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
                "sha256": sha256_file(ofac_path),
                "bytes": ofac_path.stat().st_size,
                "ethereum_like_addresses_indexed": len(sanction_addresses),
            },
            "raw_external_inputs_committed": False,
        },
        "items": decisions,
    }
    payload["screen_content_hash"] = canonical_hash(decisions)
    write_json(root / args.out, payload)
    report = {
        "checked_at": created_at,
        "gate": "stage8_negative_candidate_screen",
        "status": "ok" if not errors and len(decisions) == len(queue.get("items", [])) else "failed",
        "candidate_count": len(queue.get("items", [])),
        "screened_count": len(decisions),
        "screen_pass_human_review_required": sum(
            item["review_status"] == "screen_pass_human_review_required" for item in decisions
        ),
        "blocked_unlabeled": sum(item["review_status"] == "blocked_unlabeled" for item in decisions),
        "hard_negative_candidates": sum(item["hard_negative_candidate"] for item in decisions),
        "known_exploit_transaction_hash_hits": sum(
            item["known_exploit_transaction_hash_match"] for item in decisions
        ),
        "ofac_sdn_graph_address_hits": sum(
            bool(item["ofac_sdn_graph_address_hits"]) for item in decisions
        ),
        "positive_anchor_overlaps": sum(item["positive_anchor_overlap"] for item in decisions),
        "labels_promoted": 0,
        "human_review_completed": False,
        "screening_sources": payload["screening_sources"],
        "errors": errors,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
