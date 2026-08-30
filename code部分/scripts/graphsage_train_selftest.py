#!/usr/bin/env python3
"""Fast contract and metric checks for the Stage 6 GraphSAGE trainer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from graphsage_train import (
    binary_metrics,
    is_improvement,
    minibatches,
    path_within_root,
    safe_run_id,
    validate_split_manifest,
)


def manifest_fixture() -> dict:
    items = []
    for split in ("train", "validation", "held_out_test"):
        for label in (0, 1):
            items.append(
                {
                    "split": split,
                    "label": label,
                    "tx_hash": f"{split}-{label}",
                    "group_id": f"{split}-group-{label}",
                }
            )
    return {
        "schema_ver": "grouped-split-manifest.stage4.v1",
        "frozen": True,
        "items": items,
    }


def main() -> int:
    audit = validate_split_manifest(manifest_fixture())
    assert audit["item_counts"] == {"train": 2, "validation": 2, "held_out_test": 2}

    leaking = manifest_fixture()
    leaking["items"][-1]["group_id"] = leaking["items"][0]["group_id"]
    try:
        validate_split_manifest(leaking)
    except ValueError as exc:
        assert "group leakage" in str(exc)
    else:
        raise AssertionError("group leakage was accepted")

    metrics = binary_metrics([0, 1], [0.1, 0.9], threshold=0.5)
    assert metrics["pr_auc"] == 1.0, metrics
    assert metrics["roc_auc"] == 1.0, metrics
    assert metrics["f1"] == 1.0, metrics
    inverse = binary_metrics([0, 1], [0.9, 0.1], threshold=0.5)
    assert inverse["pr_auc"] == 0.5, inverse
    assert inverse["roc_auc"] == 0.0, inverse
    tied = binary_metrics([0, 0, 1], [0.0, 0.0, 0.0], threshold=0.5)
    assert tied["pr_auc"] == 1 / 3, tied

    samples = [{"id": index} for index in range(7)]
    first = [[item["id"] for item in batch] for batch in minibatches(samples, 3, seed=11)]
    second = [[item["id"] for item in batch] for batch in minibatches(samples, 3, seed=11)]
    assert first == second and sorted(sum(first, [])) == list(range(7))

    assert safe_run_id("stage6.integration-01") == "stage6.integration-01"
    try:
        safe_run_id("../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe run id was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        assert path_within_root(root, "safe.json") == root / "safe.json"
        try:
            path_within_root(root, "../escape.json")
        except ValueError:
            pass
        else:
            raise AssertionError("path escape was accepted")

    assert is_improvement(0.6, 0.5, "pr_auc")
    assert is_improvement(0.4, 0.5, "validation_loss")
    print("graphsage_train_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
