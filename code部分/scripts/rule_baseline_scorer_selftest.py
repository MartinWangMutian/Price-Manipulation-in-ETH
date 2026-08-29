#!/usr/bin/env python3
"""Synthetic checks for rule_baseline_scorer.py."""

from __future__ import annotations

from rule_baseline_scorer import abnormal_profit_path, build_risk_score, severity_for


def main() -> int:
    graph = {
        "event_id": "graph-1",
        "schema_ver": "graph-inference.v1",
        "chain_id": 1,
        "created_at": "2026-05-14T00:00:00.000+00:00",
        "idempotency_key": "1:0x" + "12" * 32 + ":graph-inference.v1",
        "graph_id": "graph:0x" + "12" * 32,
        "tx_hash": "0x" + "12" * 32,
        "nodes": [
            {"node_id": "tx:0x" + "12" * 32, "node_type": "transaction"},
            {"node_id": "address:0x" + "11" * 20, "node_type": "address"},
            {"node_id": "address:0x" + "22" * 20, "node_type": "address"},
            {
                "node_id": "asset:0x" + "33" * 20,
                "node_type": "asset",
                "symbol": "USDC",
            },
            {
                "node_id": "protocol:0x" + "44" * 20,
                "node_type": "protocol",
                "address": "0x" + "44" * 20,
                "roles": ["oracle"],
            },
            {
                "node_id": "protocol:0x" + "55" * 20,
                "node_type": "protocol",
                "address": "0x" + "55" * 20,
                "roles": ["pool"],
            },
        ],
        "edges": [
            {
                "edge_id": "e1",
                "edge_type": "transfer",
                "from_node": "address:0x" + "11" * 20,
                "to_node": "address:0x" + "22" * 20,
                "asset_node": "asset:0x" + "33" * 20,
                "value_usd": 100.0,
            },
            {
                "edge_id": "e2",
                "edge_type": "transfer",
                "from_node": "address:0x" + "22" * 20,
                "to_node": "address:0x" + "11" * 20,
                "asset_node": "asset:0x" + "33" * 20,
                "value_usd": 160.0,
            },
            {
                "edge_id": "e3",
                "edge_type": "call",
                "from_node": "address:0x" + "11" * 20,
                "to_node": "address:0x" + "55" * 20,
                "ordinal": 0,
                "semantic_action": "swap",
                "function_name": "swapExactTokensForTokens",
                "success": True,
            },
            {
                "edge_id": "e4",
                "edge_type": "call",
                "from_node": "address:0x" + "11" * 20,
                "to_node": "address:0x" + "44" * 20,
                "ordinal": 1,
                "semantic_action": "oracle_read",
                "function_name": "latestRoundData",
                "success": True,
            },
            {
                "edge_id": "e5",
                "edge_type": "call",
                "from_node": "address:0x" + "11" * 20,
                "to_node": "address:0x" + "22" * 20,
                "ordinal": 2,
                "semantic_action": "flash_loan",
                "function_name": "flashLoanSimple",
                "success": True,
            },
        ],
        "feature_ver": "cash-flow-graph-builder.v1",
        "context_windows": ["tx-only"],
        "feature_missing_flags": [],
    }
    config = {
        "model_version": "rule-baseline.v1",
        "threshold_profile": "rule-baseline-thresholds.v1",
        "severity_thresholds": {"watch": 0.5, "high": 0.75, "critical": 0.9},
        "rules": {
            "abnormal_profit_path": {
                "reason_code": "RULE_ABNORMAL_PROFIT_PATH",
                "weight": 0.35,
                "min_profit_ratio": 0.3,
                "full_score_ratio": 0.5,
            },
            "oracle_read_write_same_tx": {
                "reason_code": "RULE_ORACLE_READ_WRITE_SAME_TX",
                "weight": 0.25,
                "max_call_distance": 5,
            },
            "excessive_slippage": {
                "reason_code": "RULE_EXCESSIVE_SLIPPAGE",
                "weight": 0.2,
                "min_slippage_bps": 300,
            },
            "thin_liquidity_trade": {
                "reason_code": "RULE_THIN_LIQUIDITY_TRADE",
                "weight": 0.2,
                "max_liquidity_usd": 1000000.0,
            },
            "flash_loan_path": {
                "reason_code": "RULE_FLASH_LOAN_PATH",
                "weight": 0.3,
                "selector_hints": ["flashloan", "flash"],
            },
        },
        "fallback": {
            "model_reject_reason": "model_unavailable_rule_fallback",
            "no_rich_evidence_score": 0.05,
            "no_rich_evidence_reason": "RULE_BASELINE_NO_RICH_EVIDENCE",
        },
    }
    score = build_risk_score(graph, config)
    assert score["score"] == 0.692308, score
    assert score["severity"] == "watch", score
    assert "RULE_ABNORMAL_PROFIT_PATH" in score["reasons"], score
    assert "RULE_FLASH_LOAN_PATH" in score["reasons"], score
    assert "RULE_ORACLE_READ_WRITE_SAME_TX" in score["reasons"], score
    assert score["rule_scores"]["abnormal_profit_path"] == 1.0, score
    assert score["rule_scores"]["oracle_read_write_same_tx"] == 1.0, score
    assert score["model_reject_reason"] == "model_unavailable_rule_fallback", score
    one_way_payment = {
        "edges": [
            {
                "edge_type": "transfer",
                "from_node": "address:payer",
                "to_node": "address:recipient",
                "value_usd": 1_000.0,
            }
        ]
    }
    assert abnormal_profit_path(one_way_payment, 0.3, 0.5) == 0.0
    assert severity_for(0.9, config["severity_thresholds"]) == "critical"
    print("rule_baseline_scorer_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
