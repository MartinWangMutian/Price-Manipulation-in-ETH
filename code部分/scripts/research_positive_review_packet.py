#!/usr/bin/env python3
"""Build an analyst-facing review packet for verified attack-anchor graphs."""

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
    graphs: dict[str, tuple[Path, dict[str, Any]]],
    root: Path,
) -> tuple[dict[str, Any], str]:
    errors: list[str] = []
    items: list[dict[str, Any]] = []
    for queue_item in queue.get("items", []):
        tx_hash = str(queue_item.get("tx_hash", "")).lower()
        graph_entry = graphs.get(tx_hash)
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
                "incident_id": queue_item.get("incident_id"),
                "independent_event_group": queue_item.get("independent_event_group"),
                "explorer_url": f"https://etherscan.io/tx/{tx_hash}",
                "event_evidence": queue_item.get("event_evidence", []),
                "transaction_evidence": queue_item.get("transaction_evidence", []),
                "graph_ref": str(graph_path.relative_to(root)),
                "graph_stats": graph_stats(graph),
                "protocol_roles": roles,
                "proposed_label": 1,
                "label": None,
                "promotion_status": "not_promoted",
                "analyst_review": {
                    "status": "pending",
                    "analyst": None,
                    "reviewed_at": None,
                    "decision": None,
                    "rationale": None,
                    "event_evidence_checked": False,
                    "transaction_role_checked": False,
                    "trace_graph_checked": False,
                },
            }
        )

    packet = {
        "schema_ver": "research-positive-review-packet.stage8.v1",
        "snapshot_id": queue.get("snapshot_id"),
        "created_at": now_iso(),
        "status": "ready_for_analyst" if not errors and items else "failed",
        "labels_promoted": 0,
        "review_policy": [
            "Verify the event evidence and the exact role of this transaction.",
            "Verify trace and rich-graph lineage before promotion.",
            "A verified event does not automatically prove every candidate transaction is an attack entry.",
            "Keep a mismatched or ambiguous transaction unlabeled.",
            "Promotion requires analyst, reviewed_at, rationale, trace ref, and graph ref.",
        ],
        "items": items,
        "errors": errors,
    }
    packet["review_packet_content_hash"] = canonical_hash(items)

    lines = [
        "# Stage 8 Positive Anchor Review Packet",
        "",
        "These anchors have verified event evidence and complete rich graphs, but none is",
        "promoted automatically. Confirm the exact transaction role before assigning label 1.",
        "",
        "| Event | Transaction | Calls | Transfers | Depth | Protocol roles | Decision |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for item in items:
        stats = item["graph_stats"]
        protocols = ", ".join(
            str(role.get("protocol_id")) for role in item["protocol_roles"]
        ) or "none"
        short_hash = f"{item['tx_hash'][:10]}…{item['tx_hash'][-8:]}"
        lines.append(
            f"| {item['incident_id']} | [{short_hash}]({item['explorer_url']}) | "
            f"{stats['call_edges']} | {stats['transfer_edges']} | {stats['max_call_depth']} | "
            f"{protocols} | pending |"
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
    parser = argparse.ArgumentParser(description="Build a positive anchor review packet.")
    parser.add_argument("--queue", required=True)
    parser.add_argument("--graphs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown", required=True)
    args = parser.parse_args()
    root = Path.cwd()
    packet, markdown = build_packet(
        read_json(root / args.queue), graph_index(root / args.graphs), root
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
