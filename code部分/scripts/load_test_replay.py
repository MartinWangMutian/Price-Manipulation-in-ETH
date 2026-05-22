#!/usr/bin/env python3
"""Replay-based load test for local pipeline stages."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alert_orchestrator import build_alert, load_tx_index
from cash_flow_graph_builder import build_graph
from rule_baseline_scorer import build_risk_score


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


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)


def latency_summary(values: list[float]) -> dict[str, float | None]:
    return {
        "count": len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": round(max(values), 3) if values else None,
    }


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def tx_time_index(root: Path) -> dict[str, datetime]:
    index: dict[str, datetime] = {}
    for path in iter_json_files(root):
        record = read_json(path)
        tx_hash = record.get("tx_hash")
        timestamp = parse_time(record.get("seen_at")) or parse_time(record.get("created_at"))
        if isinstance(tx_hash, str) and timestamp is not None and tx_hash not in index:
            index[tx_hash] = timestamp
    return index


def measure_graph_builder(parsed_files: list[Path], protocol_features: dict[str, dict[str, Any]]) -> list[float]:
    latencies: list[float] = []
    for path in parsed_files:
        parsed = read_json(path)
        started = time.perf_counter()
        build_graph(parsed, protocol_features.get(parsed["idempotency_key"]))
        latencies.append((time.perf_counter() - started) * 1000)
    return latencies


def measure_rule_scorer(graph_files: list[Path], config: dict[str, Any]) -> list[float]:
    latencies: list[float] = []
    for path in graph_files:
        graph = read_json(path)
        started = time.perf_counter()
        build_risk_score(graph, config)
        latencies.append((time.perf_counter() - started) * 1000)
    return latencies


def measure_alert_orchestrator(
    risk_files: list[Path],
    routing: dict[str, Any],
    graph_index: dict[str, dict[str, Any]],
    trace_index: dict[str, dict[str, Any]],
) -> list[float]:
    latencies: list[float] = []
    for path in risk_files:
        risk = read_json(path)
        started = time.perf_counter()
        build_alert(risk, routing, graph_index, trace_index)
        latencies.append((time.perf_counter() - started) * 1000)
    return latencies


def load_protocol_features(root: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in iter_json_files(root):
        record = read_json(path)
        key = record.get("source_parsed_idempotency_key")
        if isinstance(key, str) and key not in index:
            index[key] = record
    return index


def end_to_end_latencies(pending_root: Path, alert_root: Path) -> list[float]:
    pending_times = tx_time_index(pending_root)
    values: list[float] = []
    for path in iter_json_files(alert_root):
        alert = read_json(path)
        tx_hash = alert.get("tx_hash")
        alert_time = parse_time(alert.get("created_at"))
        pending_time = pending_times.get(tx_hash)
        if pending_time is None or alert_time is None:
            continue
        values.append((alert_time - pending_time).total_seconds() * 1000)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Run replay-based local load test.")
    parser.add_argument("--pending", default="data/replay/pending-tx.v1")
    parser.add_argument("--parsed", default="data/replay/parsed-trace.v1")
    parser.add_argument("--protocol-features", default="data/replay/protocol-features.v1")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1")
    parser.add_argument("--risks", default="data/replay/risk-score.v1")
    parser.add_argument("--alerts", default="data/replay/alert-event.v1")
    parser.add_argument("--traces", default="data/replay/trace-bundle.v1")
    parser.add_argument("--rule-config", default="config/rule_baseline.json")
    parser.add_argument("--alert-config", default="config/alert_routing.json")
    parser.add_argument("--out", default="ops/reports/load-test-replay.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    parsed_files = iter_json_files(root / args.parsed)
    graph_files = iter_json_files(root / args.graphs)
    risk_files = iter_json_files(root / args.risks)
    protocol_features = load_protocol_features(root / args.protocol_features)
    rule_config = read_json(root / args.rule_config)
    alert_config = read_json(root / args.alert_config)
    graph_index = load_tx_index(root / args.graphs)
    trace_index = load_tx_index(root / args.traces)

    graph_latencies = measure_graph_builder(parsed_files, protocol_features)
    model_latencies = measure_rule_scorer(graph_files, rule_config)
    alert_latencies = measure_alert_orchestrator(risk_files, alert_config, graph_index, trace_index)
    e2e_latencies = end_to_end_latencies(root / args.pending, root / args.alerts)

    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "mode": "replay_local",
        "pending_listener": {
            "status": "not_live_load_tested",
            "note": "live pending listener load test requires node/provider stream",
        },
        "trace_worker": {
            "status": "not_live_load_tested",
            "note": "live trace worker load test requires Geth or Erigon trace endpoint",
        },
        "graph_builder_latency_ms": latency_summary(graph_latencies),
        "model_inference_latency_ms": latency_summary(model_latencies),
        "alert_orchestrator_latency_ms": latency_summary(alert_latencies),
        "end_to_end_detection_latency_ms": latency_summary(e2e_latencies),
        "counts": {
            "parsed_records": len(parsed_files),
            "graphs": len(graph_files),
            "risk_scores": len(risk_files),
            "alerts": len(iter_json_files(root / args.alerts)),
            "e2e_pairs": len(e2e_latencies),
        },
        "limitations": [
            "replay_local measures local Python processing, not live node/network load",
            "trace latency cannot be measured without Geth or Erigon trace endpoint",
            "provider-only replay has no high/critical workload mix",
        ],
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
