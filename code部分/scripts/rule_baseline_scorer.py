#!/usr/bin/env python3
"""Offline rule-baseline scorer for graph-inference replay records."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
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


def event_id_for(graph: dict[str, Any]) -> str:
    seed = f"risk-score.v1:{graph['idempotency_key']}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def severity_for(score: float, thresholds: dict[str, Any]) -> str:
    critical = float(thresholds.get("critical", 0.9))
    high = float(thresholds.get("high", 0.75))
    watch = float(thresholds.get("watch", 0.5))
    if score >= critical:
        return "critical"
    if score >= high:
        return "high"
    if score >= watch:
        return "watch"
    return "low"


def protocol_roles(graph: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for node in graph.get("nodes", []):
        if isinstance(node, dict) and node.get("node_type") == "protocol":
            for role in node.get("roles", []):
                if isinstance(role, str):
                    roles.add(role)
    return roles


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def abnormal_profit_path(
    graph: dict[str, Any],
    min_profit_ratio: float,
    full_score_ratio: float,
) -> float:
    """Return a USD-normalized profit-path score in [0, 1].

    Mixed token units are never compared directly. Transfer edges without a
    reliable ``value_usd`` are ignored, and explicitly marked flash-loan borrow
    and repay legs are excluded from profit accounting.
    """
    inflow: dict[str, float] = defaultdict(float)
    outflow: dict[str, float] = defaultdict(float)
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict) or edge.get("edge_type") != "transfer":
            continue
        if edge.get("flash_loan_leg") in {"borrow", "repay"}:
            continue
        value_usd = number(edge.get("value_usd"))
        if value_usd is None or value_usd < 0:
            continue
        sender = edge.get("from_node")
        receiver = edge.get("to_node")
        if isinstance(sender, str):
            outflow[sender] += value_usd
        if isinstance(receiver, str):
            inflow[receiver] += value_usd
    # A one-way recipient is not a profit cycle. Restrict the rule to addresses
    # that both spend and receive value inside the simulated transaction.
    ratios = [
        (inflow[address] - outflow[address]) / max(1.0, outflow[address])
        for address in set(inflow) | set(outflow)
        if inflow[address] > 0 and outflow[address] > 0
    ]
    best = max(ratios, default=0.0)
    if best <= min_profit_ratio:
        return 0.0
    span = max(full_score_ratio - min_profit_ratio, 1e-9)
    return min(1.0, (best - min_profit_ratio) / span)


def protocol_roles_by_node(graph: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("node_type") != "protocol":
            continue
        node_id = node.get("node_id")
        if isinstance(node_id, str):
            node_roles = {
                str(role) for role in node.get("roles", []) if isinstance(role, str)
            }
            result[node_id] = node_roles
            address = node.get("address")
            if isinstance(address, str):
                result[f"address:{address.lower()}"] = node_roles
    return result


def oracle_read_write_same_tx(graph: dict[str, Any], max_call_distance: int) -> float:
    """Score a price-changing call followed by an oracle read."""
    roles = protocol_roles_by_node(graph)
    calls = [
        edge for edge in graph.get("edges", [])
        if isinstance(edge, dict) and edge.get("edge_type") == "call"
    ]
    calls.sort(key=lambda edge: int(edge.get("ordinal", edge.get("call_depth", 0)) or 0))
    price_actions: list[int] = []
    oracle_reads: list[int] = []
    for index, edge in enumerate(calls):
        target_roles = roles.get(str(edge.get("to_node")), set())
        semantic = str(edge.get("semantic_action") or "")
        if semantic in {"swap", "oracle_write"} or target_roles & {"pool", "router"}:
            price_actions.append(index)
        if semantic == "oracle_read" or "oracle" in target_roles:
            oracle_reads.append(index)
    distances = [read - write for write in price_actions for read in oracle_reads if read > write]
    if not distances:
        return 0.0
    distance = min(distances)
    if distance > max_call_distance:
        return 0.0
    return max(0.2, 1.0 - (distance - 1) / max(1, max_call_distance))


def excessive_slippage(graph: dict[str, Any], min_slippage_bps: float) -> float:
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        slippage = edge.get("slippage_bps")
        try:
            if slippage is not None and float(slippage) >= min_slippage_bps:
                return min(1.0, float(slippage) / max(min_slippage_bps * 2.0, 1.0))
        except (TypeError, ValueError):
            continue
    return 0.0


def thin_liquidity_trade(graph: dict[str, Any], max_liquidity_usd: float) -> float:
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        liquidity = node.get("liquidity_usd")
        try:
            if liquidity is not None and float(liquidity) <= max_liquidity_usd:
                return min(
                    1.0,
                    max(0.1, 1.0 - float(liquidity) / max(max_liquidity_usd, 1.0)),
                )
        except (TypeError, ValueError):
            continue
    return 0.0


def flash_loan_path(graph: dict[str, Any], selector_hints: list[str]) -> float:
    lowered_hints = [hint.lower() for hint in selector_hints]
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict) or edge.get("edge_type") != "call":
            continue
        name = str(edge.get("function_name") or edge.get("function_signature") or "").lower()
        semantic = str(edge.get("semantic_action") or "").lower()
        if semantic == "flash_loan" or any(hint in name for hint in lowered_hints):
            return 1.0
    return 0.0


def evaluate_graph(
    graph: dict[str, Any], config: dict[str, Any]
) -> tuple[float, list[str], dict[str, float]]:
    rules = config["rules"]
    reasons: list[str] = []
    rule_scores: dict[str, float] = {}

    abnormal_cfg = rules["abnormal_profit_path"]
    rule_scores["abnormal_profit_path"] = abnormal_profit_path(
        graph,
        float(abnormal_cfg.get("min_profit_ratio", 0.3)),
        float(abnormal_cfg.get("full_score_ratio", 0.5)),
    )

    oracle_cfg = rules["oracle_read_write_same_tx"]
    rule_scores["oracle_read_write_same_tx"] = oracle_read_write_same_tx(
        graph, int(oracle_cfg.get("max_call_distance", 5))
    )

    slippage_cfg = rules["excessive_slippage"]
    rule_scores["excessive_slippage"] = excessive_slippage(
        graph, float(slippage_cfg["min_slippage_bps"])
    )

    liquidity_cfg = rules["thin_liquidity_trade"]
    rule_scores["thin_liquidity_trade"] = thin_liquidity_trade(
        graph, float(liquidity_cfg["max_liquidity_usd"])
    )

    flash_cfg = rules["flash_loan_path"]
    rule_scores["flash_loan_path"] = flash_loan_path(
        graph, list(flash_cfg["selector_hints"])
    )

    weighted = 0.0
    total_weight = 0.0
    for name, value in rule_scores.items():
        rule = rules[name]
        weight = float(rule["weight"])
        weighted += weight * value
        total_weight += weight
        if value > 0:
            reasons.append(rule["reason_code"])
    score = weighted / total_weight if total_weight else 0.0

    no_edges = not graph.get("edges")
    if no_edges:
        fallback = config["fallback"]
        score = max(score, float(fallback["no_rich_evidence_score"]))
        reasons.append(fallback["no_rich_evidence_reason"])
    if "trace_unsupported" in graph.get("feature_missing_flags", []):
        reasons.append("FEATURE_TRACE_UNSUPPORTED")

    return min(round(score, 6), 1.0), sorted(set(reasons)), {
        name: round(value, 6) for name, value in sorted(rule_scores.items())
    }


def score_graph(graph: dict[str, Any], config: dict[str, Any]) -> tuple[float, list[str]]:
    score, reasons, _ = evaluate_graph(graph, config)
    return score, reasons


def build_risk_score(graph: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    score, reasons, rule_scores = evaluate_graph(graph, config)
    thresholds = config["severity_thresholds"]
    return {
        "event_id": event_id_for(graph),
        "schema_ver": "risk-score.v1",
        "chain_id": graph["chain_id"],
        "created_at": now_iso(),
        "idempotency_key": f"{graph['idempotency_key']}:risk-score.v1",
        "tx_hash": graph["tx_hash"],
        "score": score,
        "severity": severity_for(score, thresholds),
        "reasons": reasons,
        "rule_scores": rule_scores,
        "model_version": config["model_version"],
        "feature_ver": graph["feature_ver"],
        "threshold_profile": config["threshold_profile"],
        "model_reject_reason": config["fallback"]["model_reject_reason"],
    }


def replay_output_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "replay"
        / "risk-score.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def rule_hit_path(root: Path, record: dict[str, Any]) -> Path:
    created = datetime.fromisoformat(record["created_at"])
    return (
        root
        / "data"
        / "rule-hits"
        / "risk-score.v1"
        / f"dt={created:%Y-%m-%d}"
        / f"hour={created:%H}"
        / f"{record['event_id']}.json"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rule-baseline scoring on graph replay files.")
    parser.add_argument("--input", default="data/replay/graph-inference.v1")
    parser.add_argument("--config", default="config/rule_baseline.json")
    parser.add_argument("--out", default="ops/reports/rule-baseline-scorer.latest.json")
    parser.add_argument("--write-replay", action="store_true")
    parser.add_argument("--write-hit-samples", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    config = read_json(root / args.config)
    seen_input_keys: set[str] = set()
    skipped_duplicates = 0
    scores: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    severity_counts = Counter()
    reason_counts = Counter()

    for path in iter_json_files(root / args.input):
        try:
            graph = read_json(path)
            key = graph.get("idempotency_key")
            if not isinstance(key, str):
                errors.append({"path": str(path), "error": "missing idempotency_key"})
                continue
            if key in seen_input_keys:
                skipped_duplicates += 1
                continue
            seen_input_keys.add(key)
            record = build_risk_score(graph, config)
            scores.append(record)
            severity_counts[record["severity"]] += 1
            for reason in record["reasons"]:
                reason_counts[reason] += 1
            if args.write_replay:
                write_json(replay_output_path(root, record), record)
            rule_reasons = [
                reason
                for reason in record["reasons"]
                if reason.startswith("RULE_") and reason != config["fallback"]["no_rich_evidence_reason"]
            ]
            if args.write_hit_samples and rule_reasons:
                write_json(rule_hit_path(root, record), {"risk_score": record, "graph": graph})
        except Exception as exc:  # noqa: BLE001 - report all scoring failures.
            errors.append({"path": str(path), "error": str(exc)})

    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "input": args.input,
        "files_seen": len(iter_json_files(root / args.input)),
        "unique_graphs": len(seen_input_keys),
        "skipped_duplicate_graphs": skipped_duplicates,
        "risk_scores_written": len(scores) if args.write_replay else 0,
        "scores_generated": len(scores),
        "severity_counts": dict(sorted(severity_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "model_version": config["model_version"],
        "threshold_profile": config["threshold_profile"],
        "model_reject_reason": config["fallback"]["model_reject_reason"],
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
