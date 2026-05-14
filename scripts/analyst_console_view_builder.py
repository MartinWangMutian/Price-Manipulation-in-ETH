#!/usr/bin/env python3
"""Build local analyst console view-models from replay artifacts."""

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


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def iter_json_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.json"))


def load_index(root: Path, key: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        record = read_json(path)
        value = record.get(key)
        if isinstance(value, str) and value not in index:
            index[value] = {"path": str(path), "record": record}
    return index


def ref_id(ref: str, prefix: str) -> str | None:
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return None


def find_ref(alert: dict[str, Any], prefix: str) -> str | None:
    for ref in alert.get("evidence_refs", []):
        value = ref_id(str(ref), prefix)
        if value:
            return value
    return None


def build_alert_list_item(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "alert_id": alert["alert_id"],
        "event_id": alert["event_id"],
        "tx_hash": alert["tx_hash"],
        "created_at": alert["created_at"],
        "severity": alert["severity"],
        "score": alert["score"],
        "reasons": alert.get("reasons", []),
        "review_state": alert.get("review_state", "new"),
        "suggested_actions": alert.get("suggested_actions", []),
    }


def build_detail(
    alert: dict[str, Any],
    risk_by_event: dict[str, dict[str, Any]],
    graph_by_event: dict[str, dict[str, Any]],
    trace_by_event: dict[str, dict[str, Any]],
    rag_by_alert: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    risk_ref = find_ref(alert, "risk-score:")
    graph_ref = find_ref(alert, "graph:")
    trace_ref = find_ref(alert, "trace:")
    risk = risk_by_event.get(risk_ref or "", {}).get("record")
    graph = graph_by_event.get(graph_ref or "", {}).get("record")
    trace = trace_by_event.get(trace_ref or "", {}).get("record")
    rag = rag_by_alert.get(alert["alert_id"], {}).get("record")
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    call_edges = [edge for edge in edges if isinstance(edge, dict) and edge.get("edge_type") == "call"]
    transfer_edges = [
        edge for edge in edges if isinstance(edge, dict) and edge.get("edge_type") == "transfer"
    ]
    critical_path = sorted(call_edges, key=lambda edge: edge.get("depth") or 0)[:10]
    return {
        "schema_ver": "analyst-alert-detail.v1",
        "built_at": now_iso(),
        "alert": alert,
        "transaction": {
            "chain_id": alert["chain_id"],
            "tx_hash": alert["tx_hash"],
            "trace_status": trace.get("trace_status") if isinstance(trace, dict) else None,
            "trace_source": trace.get("trace_source") if isinstance(trace, dict) else None,
        },
        "pending_simulation": {
            "status": trace.get("trace_status") if isinstance(trace, dict) else "missing",
            "calls": len(trace.get("calls", [])) if isinstance(trace, dict) else 0,
            "logs": len(trace.get("logs", [])) if isinstance(trace, dict) else 0,
            "feature_missing_flags": graph.get("feature_missing_flags", []) if isinstance(graph, dict) else [],
        },
        "cash_flow_graph": {
            "graph_id": graph.get("graph_id") if isinstance(graph, dict) else None,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "transfer_edge_count": len(transfer_edges),
            "call_edge_count": len(call_edges),
            "snapshot_ref": graph.get("graph_snapshot_ref") if isinstance(graph, dict) else None,
        },
        "critical_path": critical_path,
        "reason_codes": alert.get("reasons", []),
        "model_metadata": {
            "model_version": risk.get("model_version") if isinstance(risk, dict) else None,
            "feature_ver": risk.get("feature_ver") if isinstance(risk, dict) else None,
            "threshold_profile": risk.get("threshold_profile") if isinstance(risk, dict) else None,
            "model_reject_reason": risk.get("model_reject_reason") if isinstance(risk, dict) else None,
        },
        "rag_evidence": {
            "graph_summary": rag.get("graph_summary") if isinstance(rag, dict) else None,
            "doc_summary": rag.get("doc_summary") if isinstance(rag, dict) else None,
            "analyst_note": rag.get("analyst_note") if isinstance(rag, dict) else None,
            "evidence_refs": rag.get("evidence_refs", []) if isinstance(rag, dict) else [],
        },
        "label_evidence": [ref for ref in alert.get("evidence_refs", []) if str(ref).startswith("label:")],
        "suggested_actions": alert.get("suggested_actions", []),
        "review": {
            "state": alert.get("review_state", "new"),
            "operator": "system",
            "state_changed_at": alert.get("created_at"),
            "reason": "initial alert replay import",
            "evidence_refs": alert.get("evidence_refs", []),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build analyst console local view-models.")
    parser.add_argument("--alerts", default="data/replay/alert-event.v1")
    parser.add_argument("--risks", default="data/replay/risk-score.v1")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1")
    parser.add_argument("--traces", default="data/replay/trace-bundle.v1")
    parser.add_argument("--rag", default="data/replay/rag-explanation.v1")
    parser.add_argument("--out-dir", default="data/console")
    parser.add_argument("--audit-trail", default="data/console/review-audit-trail.v1.jsonl")
    parser.add_argument("--report", default="ops/reports/analyst-console-view-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    alert_files = iter_json_files(root / args.alerts)
    risk_by_event = load_index(root / args.risks, "event_id")
    graph_by_event = load_index(root / args.graphs, "event_id")
    trace_by_event = load_index(root / args.traces, "event_id")
    rag_by_alert = load_index(root / args.rag, "alert_id")
    out_dir = root / args.out_dir
    detail_dir = out_dir / "alerts-detail.v1"
    list_items: list[dict[str, Any]] = []
    severity_counts = Counter()
    review_counts = Counter()
    errors: list[dict[str, Any]] = []

    for path in alert_files:
        try:
            alert = read_json(path)
            list_items.append(build_alert_list_item(alert))
            detail = build_detail(alert, risk_by_event, graph_by_event, trace_by_event, rag_by_alert)
            write_json(detail_dir / f"{alert['event_id']}.json", detail)
            append_jsonl(root / args.audit_trail, detail["review"])
            severity_counts[alert["severity"]] += 1
            review_counts[alert.get("review_state", "new")] += 1
        except Exception as exc:  # noqa: BLE001 - report all view build errors.
            errors.append({"path": str(path), "error": str(exc)})

    list_payload = {
        "schema_ver": "analyst-alert-list.v1",
        "built_at": now_iso(),
        "alerts": sorted(list_items, key=lambda item: item["created_at"], reverse=True),
    }
    write_json(out_dir / "alerts-list.v1.json", list_payload)
    audit_export = {
        "schema_ver": "review-audit-trail-export.v1",
        "exported_at": now_iso(),
        "audit_trail": args.audit_trail,
        "entries": len(list_items),
    }
    write_json(out_dir / "review-audit-trail-export.v1.json", audit_export)

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "alerts_seen": len(alert_files),
        "list_items": len(list_items),
        "detail_views": len(list_items),
        "severity_counts": dict(sorted(severity_counts.items())),
        "review_state_counts": dict(sorted(review_counts.items())),
        "outputs": [
            "data/console/alerts-list.v1.json",
            "data/console/alerts-detail.v1/",
            "data/console/review-audit-trail.v1.jsonl",
            "data/console/review-audit-trail-export.v1.json",
        ],
        "errors": errors,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
