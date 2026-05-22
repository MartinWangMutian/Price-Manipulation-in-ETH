#!/usr/bin/env python3
"""Build evidence-constrained rag-explanation events from alerts."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_retriever import retrieve


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


def load_tx_index(root: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        record = read_json(path)
        tx_hash = record.get("tx_hash")
        if isinstance(tx_hash, str) and tx_hash not in index:
            index[tx_hash] = {"path": str(path), "record": record}
    return index


def event_id_for(alert: dict[str, Any]) -> str:
    seed = f"rag-explanation.v1:{alert['idempotency_key']}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def query_for(alert: dict[str, Any]) -> str:
    return " ".join([alert.get("severity", ""), *alert.get("reasons", [])]).replace("_", " ")


def sentence_with_ref(text: str, refs: list[str]) -> str | None:
    if not refs:
        return None
    ref_text = " ".join(f"[{ref}]" for ref in refs)
    return f"{text} {ref_text}"


def graph_summary(alert: dict[str, Any], graph_index: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    graph_entry = graph_index.get(alert["tx_hash"])
    if graph_entry is None:
        ref = "graph:missing"
        text = f"Graph evidence is missing for tx {alert['tx_hash']}."
        sentence = sentence_with_ref(text, [ref])
        return sentence or "", [ref]
    graph = graph_entry["record"]
    graph_ref = f"graph:{graph['event_id']}"
    text = (
        f"Graph evidence for tx {alert['tx_hash']} has "
        f"{len(graph.get('nodes', []))} nodes and {len(graph.get('edges', []))} edges."
    )
    sentence = sentence_with_ref(text, [graph_ref])
    refs = [graph_ref]
    snapshot = graph.get("graph_snapshot_ref")
    if isinstance(snapshot, str):
        refs.append(f"graph-snapshot:{snapshot}")
    return sentence or "", refs


def doc_summary(retrieval: dict[str, Any]) -> tuple[str, list[str]]:
    if retrieval.get("null_retrieval"):
        ref = f"knowledge:{retrieval.get('knowledge_snapshot', 'unknown')}:null"
        text = f"No RAG document matched query '{retrieval.get('query')}'."
        sentence = sentence_with_ref(text, [ref])
        return sentence or "", [ref]
    sentences: list[str] = []
    refs: list[str] = []
    for hit in retrieval.get("hits", [])[:3]:
        ref = hit["evidence_ref"]
        text = (
            f"Retrieved {hit['protocol']} {hit['section']} from {hit['source_type']} "
            f"with RRF score {hit['rrf_score']}."
        )
        sentence = sentence_with_ref(text, [ref])
        if sentence:
            sentences.append(sentence)
            refs.append(ref)
    return " ".join(sentences), refs


def analyst_note(alert: dict[str, Any]) -> tuple[str, list[str]]:
    alert_ref = f"alert:{alert['event_id']}"
    text = (
        f"Use the alert score {alert['score']}, severity {alert['severity']}, "
        f"and reason codes {', '.join(alert.get('reasons', []))} without rewriting them."
    )
    sentence = sentence_with_ref(text, [alert_ref])
    return sentence or "", [alert_ref]


def build_explanation(
    alert: dict[str, Any],
    graph_index: dict[str, dict[str, Any]],
    rag_index: dict[str, Any],
    knowledge_snapshot: str,
    rag_model: str,
    top_k: int,
    timeout_ms: int,
    simulate_timeout: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    retrieval: dict[str, Any]
    timeout = False
    if simulate_timeout:
        timeout = True
        retrieval = {
            "query": query_for(alert),
            "null_retrieval": True,
            "null_reason": "rag_timeout",
            "hits": [],
            "knowledge_snapshot": knowledge_snapshot,
        }
    else:
        retrieval = retrieve(rag_index, query_for(alert), top_k=top_k)
        retrieval["knowledge_snapshot"] = knowledge_snapshot
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms > timeout_ms:
            timeout = True
            retrieval = {
                "query": query_for(alert),
                "null_retrieval": True,
                "null_reason": "rag_timeout",
                "hits": [],
                "knowledge_snapshot": knowledge_snapshot,
            }

    graph_text, graph_refs = graph_summary(alert, graph_index)
    doc_text, doc_refs = doc_summary(retrieval)
    note_text, note_refs = analyst_note(alert)
    evidence_refs = sorted(set(graph_refs + doc_refs + note_refs + alert.get("evidence_refs", [])))

    return {
        "event_id": event_id_for(alert),
        "schema_ver": "rag-explanation.v1",
        "chain_id": alert["chain_id"],
        "created_at": now_iso(),
        "idempotency_key": f"{alert['idempotency_key']}:rag-explanation.v1",
        "alert_id": alert["alert_id"],
        "tx_hash": alert["tx_hash"],
        "graph_summary": graph_text,
        "doc_summary": doc_text,
        "analyst_note": note_text,
        "evidence_refs": evidence_refs,
        "knowledge_snapshot": knowledge_snapshot,
        "rag_model": rag_model,
        "timeout": timeout,
    }


def replay_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "replay"
        / "rag-explanation.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RAG explanations from alerts.")
    parser.add_argument("--alerts", default="data/replay/alert-event.v1")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1")
    parser.add_argument("--rag-index", default="data/rag/index/knowledge-snapshot.seed-2026-05-14.json")
    parser.add_argument("--templates", default="config/rag_explanation_templates.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout-ms", type=int, default=2500)
    parser.add_argument("--include-low", action="store_true")
    parser.add_argument("--simulate-timeout", action="store_true")
    parser.add_argument("--write-replay", action="store_true")
    parser.add_argument("--audit-log", default="ops/audit/rag-explanation-builder.jsonl")
    parser.add_argument("--out", default="ops/reports/rag-explanation-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    graph_index = load_tx_index(root / args.graphs)
    rag_index = read_json(root / args.rag_index)
    templates = read_json(root / args.templates)
    knowledge_snapshot = templates["knowledge_snapshot"]
    rag_model = templates["rag_model"]

    seen_input_keys: set[str] = set()
    skipped_duplicates = 0
    explanations: list[dict[str, Any]] = []
    skipped_by_severity = 0
    errors: list[dict[str, Any]] = []
    timeout_counts = Counter()
    severity_counts = Counter()

    for path in iter_json_files(root / args.alerts):
        try:
            alert = read_json(path)
            key = alert.get("idempotency_key")
            if not isinstance(key, str):
                errors.append({"path": str(path), "error": "missing idempotency_key"})
                continue
            if key in seen_input_keys:
                skipped_duplicates += 1
                continue
            seen_input_keys.add(key)
            if alert.get("severity") not in {"high", "critical"} and not args.include_low:
                skipped_by_severity += 1
                continue
            explanation = build_explanation(
                alert,
                graph_index,
                rag_index,
                knowledge_snapshot,
                rag_model,
                args.top_k,
                args.timeout_ms,
                args.simulate_timeout,
            )
            explanations.append(explanation)
            severity_counts[alert.get("severity", "unknown")] += 1
            timeout_counts["timeout" if explanation["timeout"] else "ok"] += 1
            if args.write_replay:
                write_json(replay_output_path(root, explanation), explanation)
            append_jsonl(
                root / args.audit_log,
                {
                    "created_at": now_iso(),
                    "stage": "rag-explanation-builder",
                    "alert_id": alert.get("alert_id"),
                    "alert_event_id": alert.get("event_id"),
                    "explanation_event_id": explanation["event_id"],
                    "tx_hash": alert.get("tx_hash"),
                    "timeout": explanation["timeout"],
                    "evidence_ref_count": len(explanation["evidence_refs"]),
                },
            )
        except Exception as exc:  # noqa: BLE001 - report all failures.
            errors.append({"path": str(path), "error": str(exc)})

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "alerts_seen": len(iter_json_files(root / args.alerts)),
        "unique_alerts": len(seen_input_keys),
        "skipped_duplicate_alerts": skipped_duplicates,
        "skipped_by_severity": skipped_by_severity,
        "explanations_generated": len(explanations),
        "explanations_written": len(explanations) if args.write_replay else 0,
        "severity_counts": dict(sorted(severity_counts.items())),
        "timeout_counts": dict(sorted(timeout_counts.items())),
        "knowledge_snapshot": knowledge_snapshot,
        "rag_model": rag_model,
        "audit_log": args.audit_log,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
