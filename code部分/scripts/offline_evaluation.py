#!/usr/bin/env python3
"""Build offline replay/evaluation reports from local replay artifacts."""

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


def load_index(root: Path, key: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        record = read_json(path)
        value = record.get(key)
        if isinstance(value, str) and value not in index:
            index[value] = {"path": str(path), "record": record}
    return index


def ref_exists(ref: str, indexes: dict[str, dict[str, dict[str, Any]]]) -> bool:
    if ":" not in ref:
        return False
    prefix, value = ref.split(":", 1)
    if prefix == "graph-snapshot":
        return Path(value).exists()
    if prefix == "label" and value == "none":
        return True
    return value in indexes.get(prefix, {})


def high_critical(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [alert for alert in alerts if alert.get("severity") in {"high", "critical"}]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local offline evaluation over replay outputs.")
    parser.add_argument("--alerts", default="data/replay/alert-event.v1")
    parser.add_argument("--risks", default="data/replay/risk-score.v1")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1")
    parser.add_argument("--traces", default="data/replay/trace-bundle.v1")
    parser.add_argument("--rag", default="data/replay/rag-explanation.v1")
    parser.add_argument("--incidents", default="data/training/positive_incidents.seed.json")
    parser.add_argument("--label-snapshot", default="data/training/label_snapshot.v1.json")
    parser.add_argument("--out-dir", default="data/evaluation")
    parser.add_argument("--report", default="ops/reports/offline-evaluation.latest.json")
    parser.add_argument(
        "--threshold-report", default="ops/reports/threshold-calibration.latest.json"
    )
    args = parser.parse_args()

    root = Path.cwd()
    alerts = [read_json(path) for path in iter_json_files(root / args.alerts)]
    risks = [read_json(path) for path in iter_json_files(root / args.risks)]
    graphs = [read_json(path) for path in iter_json_files(root / args.graphs)]
    incidents = read_json(root / args.incidents).get("incidents", [])
    label_snapshot = read_json(root / args.label_snapshot)

    indexes = {
        "risk-score": load_index(root / args.risks, "event_id"),
        "graph": load_index(root / args.graphs, "event_id"),
        "trace": load_index(root / args.traces, "event_id"),
        "alert": load_index(root / args.alerts, "event_id"),
    }
    rag_by_alert = load_index(root / args.rag, "alert_id")

    evidence_refs_seen = 0
    evidence_refs_valid = 0
    invalid_refs: list[dict[str, Any]] = []
    for alert in alerts:
        for ref in alert.get("evidence_refs", []):
            evidence_refs_seen += 1
            if ref_exists(str(ref), indexes):
                evidence_refs_valid += 1
            else:
                invalid_refs.append({"alert_id": alert.get("alert_id"), "ref": ref})

    hc_alerts = high_critical(alerts)
    hc_with_graph = [
        alert
        for alert in hc_alerts
        if any(str(ref).startswith("graph:") for ref in alert.get("evidence_refs", []))
    ]
    hc_with_explanation = [
        alert for alert in hc_alerts if alert.get("alert_id") in rag_by_alert
    ]
    severity_counts = Counter(alert.get("severity", "unknown") for alert in alerts)
    reason_counts = Counter(
        reason for alert in alerts for reason in alert.get("reasons", [])
    )
    score_buckets = Counter()
    for risk in risks:
        score = float(risk.get("score", 0.0))
        if score < 0.5:
            score_buckets["<0.50"] += 1
        elif score < 0.75:
            score_buckets["0.50-0.75"] += 1
        elif score <= 0.9:
            score_buckets["0.75-0.90"] += 1
        else:
            score_buckets[">0.90"] += 1

    exploit_replay_set = {
        "schema_ver": "exploit-replay-set.v1",
        "created_at": now_iso(),
        "items": [
            {
                "incident_id": incident["incident_id"],
                "chain": incident["chain"],
                "attack_type": incident["attack_type"],
                "affected_protocol": incident["affected_protocol"],
                "key_transactions": incident.get("key_transactions", []),
                "replay_status": incident.get("replay_status"),
            }
            for incident in incidents
        ],
    }
    provider_unlabeled_set = {
        "schema_ver": "provider-unlabeled-eval-set.v1",
        "created_at": now_iso(),
        "items": [
            {
                "tx_hash": graph.get("tx_hash"),
                "graph_event_id": graph.get("event_id"),
                "feature_missing_flags": graph.get("feature_missing_flags", []),
            }
            for graph in graphs
            if "trace_unsupported" in graph.get("feature_missing_flags", [])
        ],
    }
    out_dir = root / args.out_dir
    write_json(out_dir / "exploit-replay-set.seed.v1.json", exploit_replay_set)
    write_json(out_dir / "provider-unlabeled-eval-set.v1.json", provider_unlabeled_set)

    evaluation_report = {
        "checked_at": now_iso(),
        "status": "ok" if not invalid_refs else "failed",
        "alerts_replayed": len(alerts),
        "risk_scores": len(risks),
        "graphs": len(graphs),
        "exploit_replay_seed_incidents": len(incidents),
        "provider_unlabeled_eval_txs": len(provider_unlabeled_set["items"]),
        "severity_counts": dict(sorted(severity_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "false_positives": None,
        "false_negatives": None,
        "lead_time": None,
        "threshold_stability": {
            "score_buckets": dict(sorted(score_buckets.items())),
            "note": "provider-only replay has no confirmed labels; stability is distribution-only",
        },
        "high_critical_graph_evidence_coverage": {
            "eligible_alerts": len(hc_alerts),
            "covered_alerts": len(hc_with_graph),
            "coverage": None if not hc_alerts else len(hc_with_graph) / len(hc_alerts),
        },
        "high_critical_explanation_availability": {
            "eligible_alerts": len(hc_alerts),
            "covered_alerts": len(hc_with_explanation),
            "coverage": None if not hc_alerts else len(hc_with_explanation) / len(hc_alerts),
        },
        "evidence_ref_validity": {
            "refs_seen": evidence_refs_seen,
            "refs_valid": evidence_refs_valid,
            "coverage": None if not evidence_refs_seen else evidence_refs_valid / evidence_refs_seen,
            "invalid_refs": invalid_refs,
        },
        "blocking_reasons": [
            "confirmed false-positive and false-negative counts require labeled normal and exploit replay sets",
            "lead time requires attack timeline labels and first-detection timestamps",
            "rich graph evidence coverage requires Geth or Erigon trace replay",
        ],
        "label_snapshot_training_ready": label_snapshot.get("training_ready"),
    }
    write_json(root / args.report, evaluation_report)

    threshold_report = {
        "checked_at": now_iso(),
        "status": "ok",
        "threshold_profile": "rule-baseline-thresholds.v1",
        "severity_counts": dict(sorted(severity_counts.items())),
        "score_buckets": dict(sorted(score_buckets.items())),
        "calibration_ready": False,
        "blocking_reasons": [
            "no confirmed positive graph replay set",
            "no confirmed stratified normal complex transaction set",
        ],
    }
    write_json(root / args.threshold_report, threshold_report)
    print(json.dumps(evaluation_report, indent=2, sort_keys=True))
    return 0 if evaluation_report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
