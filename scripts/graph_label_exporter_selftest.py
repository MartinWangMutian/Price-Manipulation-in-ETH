#!/usr/bin/env python3
"""Synthetic checks for graph_label_exporter.py."""

from __future__ import annotations

from graph_label_exporter import build_label, promoted_items


def main() -> int:
    tx_pos = "0x" + "11" * 32
    tx_neg = "0x" + "22" * 32
    decisions = {
        "exploit_decisions": [
            {
                "decision": "promoted",
                "promotion_status": "promoted",
                "tx_hash": tx_pos,
                "candidate_label": 1,
                "incident_id": "incident",
                "candidate_role": "attack_tx",
                "queue_id": "q1",
                "analyst": "analyst",
                "reviewed_at": "2026-05-14T00:00:00.000+00:00",
                "trace_bundle_ref": "trace.json",
            }
        ],
        "normal_decisions": [
            {
                "decision": "promoted",
                "promotion_status": "promoted",
                "tx_hash": tx_neg,
                "candidate_label": 0,
                "incident_id": "normal_candidate",
                "candidate_role": "normal_candidate",
                "queue_id": "q2",
                "analyst": "analyst",
                "reviewed_at": "2026-05-14T00:00:00.000+00:00",
                "trace_bundle_ref": "trace-normal.json",
            }
        ],
    }
    items = promoted_items(decisions)
    assert len(items) == 2
    graph_index = {
        tx_pos.lower(): {
            "graph_event_id": "g1",
            "graph_path": "graph-pos.json",
            "feature_ver": "cash-flow-graph-builder.v1",
            "context_windows": ["tx-only", "5m-address"],
            "feature_missing_flags": [],
        },
        tx_neg.lower(): {
            "graph_event_id": "g2",
            "graph_path": "graph-neg.json",
            "feature_ver": "cash-flow-graph-builder.v1",
            "context_windows": ["tx-only"],
            "feature_missing_flags": [],
        },
    }
    labels = [build_label(item, graph_index)[0] for item in items]
    assert {item["label"] for item in labels if item} == {0, 1}, labels
    assert labels[0]["graph_event_id"] == "g1", labels
    print("graph_label_exporter_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
