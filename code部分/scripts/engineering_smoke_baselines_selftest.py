#!/usr/bin/env python3
"""Fast feature and comparison checks for Stage 7 engineering baselines."""

from __future__ import annotations

from engineering_smoke_baselines import (
    POOLED_FEATURE_DIM,
    comparison_rows,
    pooled_feature,
    validate_config,
)
from graphsage_model import dependency_status, require_torch_stack


def main() -> int:
    config = {
        "schema_ver": "engineering-smoke.stage7.v1",
        "training_scope": "engineering_smoke_only",
        "held_out_test_policy": "prohibited_until_model_and_threshold_freeze",
        "pooled_mlp": {
            "batch_size": 8,
            "hidden_dim": 16,
            "lr": 0.001,
            "epochs": 3,
            "patience": 1,
            "gradient_clip": 1.0,
            "dropout": 0.1,
            "monitor": "pr_auc",
        },
    }
    validate_config(config)
    metrics = {
        "rule": {"validation": {"pr_auc": 0.5, "roc_auc": 0.5, "precision": 0.0,
                                  "recall": 0.0, "f1": 0.0, "brier_score": 0.2}},
        "mlp": {"validation": {"pr_auc": 0.8, "roc_auc": 0.7, "precision": 1.0,
                                 "recall": 0.5, "f1": 2 / 3, "brier_score": 0.1}},
    }
    assert comparison_rows(metrics)[0]["model"] == "mlp"

    if all(dependency_status().values()):
        torch, _, _, _ = require_torch_stack()
        graph = {
            "nodes": [
                {"node_id": "address:a", "node_type": "address"},
                {"node_id": "protocol:p", "node_type": "protocol", "roles": ["pool"]},
            ],
            "edges": [
                {
                    "edge_type": "call",
                    "from_node": "address:a",
                    "to_node": "protocol:p",
                    "semantic_action": "swap",
                }
            ],
        }
        feature = pooled_feature(torch, graph)
        assert feature.numel() == POOLED_FEATURE_DIM
        assert bool(torch.isfinite(feature).all())
    print("engineering_smoke_baselines_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
