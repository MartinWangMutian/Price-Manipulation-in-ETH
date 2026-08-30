#!/usr/bin/env python3
"""Build an analyst-facing Stage 8 negative-candidate review packet."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_expansion_builder import canonical_hash, read_json, write_json
from stage4_label_review_builder import graph_stats


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def graph_index(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(root.rglob("*.json")):
        graph = read_json(path)
        tx_hash = graph.get("tx_hash")
        if not isinstance(tx_hash, str):
            continue
        key = tx_hash.lower()
        if key in result:
            raise ValueError(f"duplicate graph for {key}")
        result[key] = (path, graph)
    return result


def build_packet(
    queue: dict[str, Any],
    screen: dict[str, Any],
    graphs: dict[str, tuple[Path, dict[str, Any]]],
    root: Path,
) -> tuple[dict[str, Any], str]:
    screen_index = {
        str(item.get("tx_hash", "")).lower(): item for item in screen.get("items", [])
    }
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    for queue_item in queue.get("items", []):
        tx_hash = str(queue_item.get("tx_hash", "")).lower()
        screen_item = screen_index.get(tx_hash)
        graph_entry = graphs.get(tx_hash)
        if screen_item is None:
            errors.append(f"missing screen result for {tx_hash}")
            continue
        if graph_entry is None:
            errors.append(f"missing graph for {tx_hash}")
            continue
        graph_path, graph = graph_entry
        roles = [
            {
                "address": node.get("address"),
                "protocol_id": node.get("protocol_id"),
                "contract": node.get("contract"),
                "roles": node.get("roles", []),
            }
            for node in graph.get("nodes", [])
            if isinstance(node, dict) and node.get("node_type") == "protocol"
        ]
        items.append(
            {
                "tx_hash": tx_hash,
                "explorer_url": f"https://etherscan.io/tx/{tx_hash}",
                "matched_incident_id": queue_item.get("matched_incident_id"),
                "block_number": queue_item.get("block_number"),
                "block_offset": queue_item.get("block_offset"),
                "from": queue_item.get("from"),
                "to": queue_item.get("to"),
                "gas": queue_item.get("gas"),
                "value": queue_item.get("value"),
                "input_bytes": queue_item.get("input_bytes"),
                "metadata_match_score": queue_item.get("metadata_match_score"),
                "graph_ref": str(graph_path.relative_to(root)),
                "graph_stats": graph_stats(graph),
                "protocol_roles": roles,
                "external_screen": {
                    "known_exploit_transaction_hash_match": screen_item.get(
                        "known_exploit_transaction_hash_match"
                    ),
                    "ofac_sdn_graph_address_hits": screen_item.get(
                        "ofac_sdn_graph_address_hits", []
                    ),
                    "positive_anchor_overlap": screen_item.get("positive_anchor_overlap"),
                    "blockers": screen_item.get("blockers", []),
                },
                "hard_negative_candidate": screen_item.get("hard_negative_candidate", False),
                "candidate_label": None,
                "promotion_status": "not_promoted",
                "analyst_review": {
                    "status": "pending",
                    "analyst": None,
                    "reviewed_at": None,
                    "decision": None,
                    "rationale": None,
                    "explorer_checked": False,
                    "protocol_context_checked": False,
                    "known_incident_search_checked": False,
                },
            }
        )

    created_at = now_iso()
    packet = {
        "schema_ver": "research-negative-review-packet.stage8.v1",
        "snapshot_id": queue.get("snapshot_id"),
        "created_at": created_at,
        "status": "ready_for_analyst" if not errors and items else "failed",
        "candidate_label": None,
        "labels_promoted": 0,
        "review_policy": [
            "A screen pass is not evidence that a transaction is benign.",
            "Open the explorer record and verify the transaction purpose and counterparties.",
            "Search for incident, sanctions, and suspicious-address evidence beyond exact matches.",
            "Keep ambiguous candidates unlabeled; do not force a negative decision.",
            "A negative label requires analyst, reviewed_at, rationale, trace ref, and graph ref.",
        ],
        "items": items,
        "errors": errors,
    }
    packet["review_packet_content_hash"] = canonical_hash(items)

    lines = [
        "# Stage 8 Negative Candidate Review Packet",
        "",
        "All five records remain unlabeled. Complete the analyst fields in the JSON packet only",
        "after checking the linked transaction, protocol context, and known-incident evidence.",
        "Ambiguous records must remain unlabeled.",
        "",
        "| Transaction | Calls | Transfers | Depth | Protocol roles | Hard candidate | Decision |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for item in items:
        stats = item["graph_stats"]
        protocols = ", ".join(
            str(role.get("protocol_id")) for role in item["protocol_roles"]
        ) or "none"
        short_hash = f"{item['tx_hash'][:10]}…{item['tx_hash'][-8:]}"
        lines.append(
            f"| [{short_hash}]({item['explorer_url']}) | {stats['call_edges']} | "
            f"{stats['transfer_edges']} | {stats['max_call_depth']} | {protocols} | "
            f"{'yes' if item['hard_negative_candidate'] else 'no'} | pending |"
        )
    lines.extend(
        [
            "",
            f"Packet hash: `{packet['review_packet_content_hash']}`",
            "",
            "No label promotion is performed by this packet.",
        ]
    )
    return packet, "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a negative candidate review packet.")
    parser.add_argument(
        "--queue", default="data/training/research_pilot_negative_trace_queue.stage8.v1.json"
    )
    parser.add_argument(
        "--screen", default="data/training/research_negative_screen.stage8.pilot.v1.json"
    )
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1/dt=2026-08-30")
    parser.add_argument(
        "--out", default="data/training/research_negative_review_packet.stage8.pilot.v1.json"
    )
    parser.add_argument("--markdown", default="ops/research_negative_review.stage8.pilot.md")
    args = parser.parse_args()

    root = Path.cwd()
    packet, markdown = build_packet(
        read_json(root / args.queue),
        read_json(root / args.screen),
        graph_index(root / args.graphs),
        root,
    )
    write_json(root / args.out, packet)
    markdown_path = root / args.markdown
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    print(json.dumps({
        "status": packet["status"],
        "candidates": len(packet["items"]),
        "labels_promoted": packet["labels_promoted"],
        "out": args.out,
        "markdown": args.markdown,
        "errors": packet["errors"],
    }, indent=2, sort_keys=True))
    return 0 if packet["status"] == "ready_for_analyst" else 2


if __name__ == "__main__":
    raise SystemExit(main())
