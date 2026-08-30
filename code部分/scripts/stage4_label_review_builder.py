#!/usr/bin/env python3
"""Build evidence-gated Stage 4 label-promotion decisions.

The external exploit corpus and sanctions file are read-only inputs. Their raw
contents are deliberately not copied into repository artifacts; reports retain
only source identifiers, hashes, versions, counts, and exact-match outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TX_RE = re.compile(r"0x[0-9a-fA-F]{64}")
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def relative_ref(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def index_json_by_tx(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    index: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(root.rglob("*.json")):
        payload = read_json(path)
        tx_hash = payload.get("tx_hash")
        if isinstance(tx_hash, str):
            key = tx_hash.lower()
            if key in index:
                raise ValueError(f"duplicate tx_hash in {root}: {key}")
            index[key] = (path, payload)
    return index


def extract_regex_values(path: Path, pattern: re.Pattern[str]) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {match.group(0).lower() for match in pattern.finditer(text)}


def exploit_corpus_hashes(root: Path) -> set[str]:
    hashes: set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.stat().st_size > 10 * 1024 * 1024:
            continue
        hashes.update(extract_regex_values(path, TX_RE))
    return hashes


def git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def graph_stats(graph: dict[str, Any]) -> dict[str, Any]:
    edge_counts = Counter(str(edge.get("edge_type", "unknown")) for edge in graph.get("edges", []))
    call_edges = [edge for edge in graph.get("edges", []) if edge.get("edge_type") == "call"]
    failed_calls = sum(edge.get("success") is False for edge in call_edges)
    max_depth = max((int(edge.get("call_depth", edge.get("depth", 0)) or 0) for edge in call_edges), default=0)
    semantic_actions = sorted(
        {
            str(edge.get("semantic_action"))
            for edge in graph.get("edges", [])
            if edge.get("semantic_action")
        }
    )
    return {
        "nodes": len(graph.get("nodes", [])),
        "edges": len(graph.get("edges", [])),
        "call_edges": edge_counts.get("call", 0),
        "transfer_edges": edge_counts.get("transfer", 0),
        "context_edges": edge_counts.get("context", 0),
        "failed_calls": failed_calls,
        "max_call_depth": max_depth,
        "semantic_actions": semantic_actions,
    }


def is_hard_negative(stats: dict[str, Any], thresholds: dict[str, int]) -> bool:
    return any(
        (
            stats["call_edges"] >= int(thresholds["call_edges_at_least"]),
            stats["transfer_edges"] >= int(thresholds["transfer_edges_at_least"]),
            stats["max_call_depth"] >= int(thresholds["max_call_depth_at_least"]),
        )
    )


def require_index_entry(index: dict[str, tuple[Path, dict[str, Any]]], tx_hash: str, kind: str) -> tuple[Path, dict[str, Any]]:
    entry = index.get(tx_hash.lower())
    if entry is None:
        raise ValueError(f"missing {kind} for {tx_hash}")
    return entry


def common_evidence(
    root: Path,
    item: dict[str, Any],
    raw_manifest: dict[str, dict[str, Any]],
    trace_index: dict[str, tuple[Path, dict[str, Any]]],
    graph_index: dict[str, tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    tx_hash = item["tx_hash"].lower()
    trace_path, trace = require_index_entry(trace_index, tx_hash, "trace bundle")
    graph_path, graph = require_index_entry(graph_index, tx_hash, "rich graph")
    raw = raw_manifest.get(tx_hash)
    if raw is None:
        raise ValueError(f"missing raw-trace manifest entry for {tx_hash}")
    if trace.get("trace_source") != "trace_transaction" or trace.get("trace_status") != "ok":
        raise ValueError(f"invalid trace source/status for {tx_hash}")
    if not trace.get("calls"):
        raise ValueError(f"empty trace calls for {tx_hash}")
    if graph.get("feature_ver") is None or not graph.get("edges"):
        raise ValueError(f"invalid rich graph for {tx_hash}")
    return {
        "trace_bundle_ref": relative_ref(root, trace_path),
        "graph_ref": relative_ref(root, graph_path),
        "raw_trace_manifest_ref": "data/training/raw-trace-manifest.stage2.v1.json",
        "raw_trace_sha256": raw.get("raw_sha256"),
        "observed_at": trace.get("observed_at"),
        "trace_source": trace.get("trace_source"),
        "trace_call_count": len(trace.get("calls", [])),
        "graph_id": graph.get("graph_id"),
        "graph_event_id": graph.get("event_id"),
        "feature_version": graph.get("feature_ver"),
        "graph_stats": graph_stats(graph),
        "feature_missing_flags": graph.get("feature_missing_flags", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Stage 4 evidence-gated label decisions.")
    parser.add_argument("--policy", default="config/label_review_policy.stage4.v1.json")
    parser.add_argument("--exploit-queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--normal-queue", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--raw-manifest", default="data/training/raw-trace-manifest.stage2.v1.json")
    parser.add_argument("--trace-input", default="data/replay/trace-bundle.v1/dt=2026-08-29")
    parser.add_argument("--graph-input", default="data/replay/graph-inference.v1/dt=2026-08-29")
    parser.add_argument("--quality-report", default="ops/reports/rich-graph-quality-audit.latest.json")
    parser.add_argument("--exploit-corpus", required=True)
    parser.add_argument("--ofac-sdn", required=True)
    parser.add_argument("--out", default="data/training/label_promotion_decisions.stage4.v1.json")
    parser.add_argument("--report", default="ops/reports/stage4-label-review-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    policy = read_json(root / args.policy)
    exploit_queue = read_json(root / args.exploit_queue).get("items", [])
    normal_queue = read_json(root / args.normal_queue).get("items", [])
    quality = read_json(root / args.quality_report)
    if quality.get("status") != "ok" or quality.get("errors"):
        raise ValueError("strict rich-graph quality report is not clean")

    raw_payload = read_json(root / args.raw_manifest)
    raw_manifest = {entry["tx_hash"].lower(): entry for entry in raw_payload.get("entries", [])}
    trace_index = index_json_by_tx(root / args.trace_input)
    graph_index = index_json_by_tx(root / args.graph_input)
    corpus_root = Path(args.exploit_corpus)
    ofac_path = Path(args.ofac_sdn)
    corpus_tx_hashes = exploit_corpus_hashes(corpus_root)
    ofac_addresses = extract_regex_values(ofac_path, ADDRESS_RE)
    positive_tx_hashes = {item["tx_hash"].lower() for item in exploit_queue}
    policy_by_tx = {item["tx_hash"].lower(): item for item in policy.get("positive_decisions", [])}
    if set(policy_by_tx) != positive_tx_hashes:
        raise ValueError("positive policy transaction set does not match exploit queue")

    review = policy["review"]
    common_review = {
        "analyst": review["analyst"],
        "reviewer_type": review["reviewer_type"],
        "reviewed_at": review["reviewed_at"],
        "human_signoff": bool(review.get("human_signoff", False)),
        "label_scope": review["scope"],
        "label_version": policy["label_version"],
    }
    exploit_decisions: list[dict[str, Any]] = []
    for item in exploit_queue:
        tx_hash = item["tx_hash"].lower()
        evidence = common_evidence(root, item, raw_manifest, trace_index, graph_index)
        judgement = policy_by_tx[tx_hash]
        promoted = judgement["decision"] == "promoted"
        source_refs = list(item.get("source_refs", []))
        if tx_hash in corpus_tx_hashes:
            source_refs.append(
                {
                    "source_type": "known_exploit_corpus_exact_match",
                    "title": "DeFiHackLabs exact transaction-hash match",
                    "url": "https://github.com/SunWeb3Sec/DeFiHackLabs",
                }
            )
        exploit_decisions.append(
            {
                **common_review,
                **evidence,
                "queue_id": item["queue_id"],
                "tx_hash": tx_hash,
                "incident_id": item["incident_id"],
                "candidate_label": 1,
                "candidate_role": item.get("candidate_role"),
                "decision": judgement["decision"],
                "promotion_status": "promoted" if promoted else "not_promoted",
                "label_semantics": judgement["label_semantics"],
                "reason_codes": judgement["reason_codes"],
                "incident_evidence_refs": source_refs,
                "known_exploit_corpus_exact_match": tx_hash in corpus_tx_hashes,
                "notes": judgement["notes"],
            }
        )

    thresholds = policy["negative_policy"]["hard_negative_thresholds"]
    normal_decisions: list[dict[str, Any]] = []
    for item in normal_queue:
        tx_hash = item["tx_hash"].lower()
        evidence = common_evidence(root, item, raw_manifest, trace_index, graph_index)
        endpoints = sorted(
            {
                value.lower()
                for value in (item.get("from"), item.get("to"))
                if isinstance(value, str) and ADDRESS_RE.fullmatch(value)
            }
        )
        exploit_hits = [tx_hash] if tx_hash in corpus_tx_hashes else []
        sanction_hits = sorted(set(endpoints) & ofac_addresses)
        positive_overlap = tx_hash in positive_tx_hashes
        blockers = []
        if exploit_hits:
            blockers.append("known_exploit_transaction_hash_match")
        if sanction_hits:
            blockers.append("ofac_sdn_endpoint_address_match")
        if positive_overlap:
            blockers.append("positive_transaction_overlap")
        promoted = not blockers
        hard_negative = is_hard_negative(evidence["graph_stats"], thresholds)
        normal_decisions.append(
            {
                **common_review,
                **evidence,
                "queue_id": item["queue_id"],
                "tx_hash": tx_hash,
                "incident_id": item.get("incident_id", "normal_candidate"),
                "candidate_label": 0,
                "candidate_role": "normal_candidate",
                "selection_bucket": item.get("selection_bucket"),
                "decision": "promoted" if promoted else "unlabeled",
                "promotion_status": "promoted" if promoted else "not_promoted",
                "label_semantics": "hard_negative" if hard_negative else "matched_negative",
                "reason_codes": [
                    "real_trace_transaction_bundle_present",
                    "strict_rich_graph_present",
                    "known_incident_and_sanctions_exact_match_screen_complete",
                ] if promoted else blockers,
                "negative_screening": {
                    "status": "pass" if promoted else "blocked",
                    "known_exploit_tx_hits": exploit_hits,
                    "ofac_sdn_endpoint_hits": sanction_hits,
                    "positive_tx_overlap": positive_overlap,
                    "screened_endpoints": endpoints,
                },
                "incident_evidence_refs": [
                    {
                        "source_type": "known_exploit_corpus_screen",
                        "title": "DeFiHackLabs exact transaction-hash screen",
                        "url": "https://github.com/SunWeb3Sec/DeFiHackLabs",
                    },
                    {
                        "source_type": "sanctions_address_screen",
                        "title": "OFAC Sanctions List Service SDN data",
                        "url": "https://ofac.treasury.gov/sanctions-list-service",
                    },
                ],
                "notes": "Promoted only for the engineering smoke dataset; absence of exact-match hits is not a research-grade proof of benign intent." if promoted else "Held unlabeled by the negative-screening gate.",
            }
        )

    decision_counts = Counter(item["decision"] for item in exploit_decisions + normal_decisions)
    promoted_label_counts = Counter(
        str(item["candidate_label"])
        for item in exploit_decisions + normal_decisions
        if item["decision"] == "promoted"
    )
    screening = {
        "known_exploit_corpus": {
            "source": "https://github.com/SunWeb3Sec/DeFiHackLabs",
            "commit": git_commit(corpus_root),
            "transaction_hashes_indexed": len(corpus_tx_hashes),
        },
        "ofac_sdn": {
            "source": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
            "sha256": sha256_file(ofac_path),
            "bytes": ofac_path.stat().st_size,
            "ethereum_like_addresses_indexed": len(ofac_addresses),
        },
        "raw_external_inputs_committed": False,
    }
    payload = {
        "schema_ver": "label-promotion-decisions.stage4.v1",
        "created_at": now_iso(),
        "snapshot_id": policy["snapshot_id"],
        "label_version": policy["label_version"],
        "feature_version": policy["feature_version"],
        "status": "reviewed_with_unlabeled_holds",
        "training_scope": "engineering_smoke_only",
        "research_training_ready": False,
        "review": review,
        "screening_sources": screening,
        "exploit_decisions": exploit_decisions,
        "normal_decisions": normal_decisions,
        "decision_counts": dict(sorted(decision_counts.items())),
        "promoted_label_counts": dict(sorted(promoted_label_counts.items())),
    }
    payload["decision_content_hash"] = canonical_hash(
        {"exploit_decisions": exploit_decisions, "normal_decisions": normal_decisions}
    )
    write_json(root / args.out, payload)

    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "out": args.out,
        "expected_transactions": len(exploit_queue) + len(normal_queue),
        "exploit_decisions": len(exploit_decisions),
        "normal_decisions": len(normal_decisions),
        "decision_counts": dict(sorted(decision_counts.items())),
        "promoted_label_counts": dict(sorted(promoted_label_counts.items())),
        "hard_negatives": sum(item["label_semantics"] == "hard_negative" for item in normal_decisions),
        "normal_exploit_hash_hits": sum(bool(item["negative_screening"]["known_exploit_tx_hits"]) for item in normal_decisions),
        "normal_ofac_endpoint_hits": sum(bool(item["negative_screening"]["ofac_sdn_endpoint_hits"]) for item in normal_decisions),
        "held_positive_transactions": [
            {"tx_hash": item["tx_hash"], "reason_codes": item["reason_codes"]}
            for item in exploit_decisions
            if item["decision"] != "promoted"
        ],
        "screening_sources": screening,
        "research_training_ready": False,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
