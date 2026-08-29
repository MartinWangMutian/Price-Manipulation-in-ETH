#!/usr/bin/env python3
"""Synthetic fallback checks for graphsage_inference_service.py."""

from __future__ import annotations

from graphsage_inference_service import rule_fallback_record


def main() -> int:
    sender = "address:0x" + "11" * 20
    receiver = "address:0x" + "22" * 20
    graph = {
        "chain_id": 1,
        "tx_hash": "0x" + "ab" * 32,
        "idempotency_key": "1:graph-rich",
        "feature_ver": "cash-flow-graph-builder.v1",
        "nodes": [],
        "edges": [
            {
                "edge_type": "call",
                "from_node": sender,
                "to_node": receiver,
                "semantic_action": "flash_loan",
                "function_name": "flashLoanSimple",
            }
        ],
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
                "max_liquidity_usd": 1_000_000,
            },
            "flash_loan_path": {
                "reason_code": "RULE_FLASH_LOAN_PATH",
                "weight": 0.3,
                "selector_hints": ["flashloan"],
            },
        },
        "fallback": {
            "model_reject_reason": "model_unavailable_rule_fallback",
            "no_rich_evidence_score": 0.05,
            "no_rich_evidence_reason": "RULE_BASELINE_NO_RICH_EVIDENCE",
        },
    }
    record = rule_fallback_record(graph, config, "graphsage_model_artifact_missing")
    assert record["score"] > 0.05, record
    assert "RULE_FLASH_LOAN_PATH" in record["reasons"], record
    assert record["model_reject_reason"] == "graphsage_model_artifact_missing", record
    print("graphsage_inference_service_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
