#!/usr/bin/env python3
"""Audit Stage 7 GraphSAGE/baseline artifacts and held-out isolation."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engineering_smoke_baselines import CHECKPOINT_SCHEMA
from graphsage_train import TRAINING_SPLITS, path_within_root, read_json, write_json
from training_runtime import sha256_file


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Stage 7 engineering smoke artifacts.")
    parser.add_argument("--baseline-run-dir", required=True)
    parser.add_argument("--graphsage-run-dir", required=True)
    parser.add_argument(
        "--split-manifest", default="data/training/split_manifest.stage4.v1.json"
    )
    parser.add_argument("--consistency-report", required=True)
    parser.add_argument("--out", default="ops/reports/engineering-smoke-audit.stage7.latest.json")
    args = parser.parse_args()

    root = Path.cwd().resolve()
    baseline_dir = path_within_root(root, args.baseline_run_dir)
    graph_dir = path_within_root(root, args.graphsage_run_dir)
    split_manifest = read_json(path_within_root(root, args.split_manifest))
    consistency = read_json(path_within_root(root, args.consistency_report))
    errors: list[str] = []

    baseline_manifest = read_json(baseline_dir / "run_manifest.json")
    baseline_metrics = read_json(baseline_dir / "metrics.json")
    graph_manifest = read_json(graph_dir / "run_manifest.json")
    graph_metrics = read_json(graph_dir / "metrics.json")
    predictions = jsonl(baseline_dir / "predictions.jsonl")

    if baseline_manifest.get("schema_ver") != "engineering-smoke-run-manifest.stage7.v1":
        errors.append("baseline manifest schema mismatch")
    if baseline_metrics.get("schema_ver") != "engineering-smoke-metrics.stage7.v1":
        errors.append("baseline metrics schema mismatch")
    if graph_manifest.get("schema_ver") != "graphsage-run-manifest.stage6.v1":
        errors.append("GraphSAGE manifest schema mismatch")
    if graph_metrics.get("schema_ver") != "graphsage-metrics.stage6.v1":
        errors.append("GraphSAGE metrics schema mismatch")
    if consistency.get("status") != "ok":
        errors.append("inference consistency audit did not pass")

    for manifest_name, manifest in (
        ("baseline", baseline_manifest),
        ("graphsage", graph_manifest),
    ):
        contract = manifest.get("contract", {})
        for key in ("split_content_hash", "graph_data_hash", "label_content_hash"):
            if contract.get(key) != split_manifest.get(key):
                errors.append(f"{manifest_name} contract mismatch {key}")
        held_out = manifest.get("held_out_test", {})
        if held_out.get("graph_files_loaded") != 0 or held_out.get("predictions") != 0:
            errors.append(f"{manifest_name} held-out isolation failed")
        if held_out.get("evaluated") is not False:
            errors.append(f"{manifest_name} held-out evaluation flag is not false")
        for name, path_value in manifest.get("outputs", {}).items():
            path = root / path_value
            if not path.is_file():
                errors.append(f"{manifest_name} output missing {name}")
            elif sha256_file(path) != manifest.get("output_sha256", {}).get(name):
                errors.append(f"{manifest_name} output hash mismatch {name}")

    allowed_items = [
        item for item in split_manifest["items"] if item["split"] in TRAINING_SPLITS
    ]
    expected_transactions = {item["tx_hash"] for item in allowed_items}
    predicted_transactions = {item.get("tx_hash") for item in predictions}
    prediction_splits = {item.get("split") for item in predictions}
    if predicted_transactions != expected_transactions or len(predictions) != len(expected_transactions):
        errors.append("comparison prediction transaction/count mismatch")
    if not prediction_splits.issubset(set(TRAINING_SPLITS)):
        errors.append("comparison predictions contain forbidden split")
    for item in predictions:
        if set(item.get("scores", {})) != {
            "rule_baseline",
            "pooled_feature_mlp",
            "graphsage",
        }:
            errors.append("comparison prediction model score set mismatch")
            break

    models = baseline_metrics.get("models", {})
    if set(models) != {"rule_baseline", "pooled_feature_mlp", "graphsage"}:
        errors.append("comparison metrics model set mismatch")
    for row in baseline_metrics.get("comparison", []):
        for key, value in row.items():
            if key != "model" and not math.isfinite(float(value)):
                errors.append(f"non-finite comparison metric {row.get('model')}:{key}")

    checkpoint_audit: dict[str, Any] = {}
    try:
        import torch

        for name in ("best_model.pt", "last_model.pt"):
            checkpoint = torch.load(baseline_dir / name, map_location="cpu", weights_only=False)
            if checkpoint.get("schema_ver") != CHECKPOINT_SCHEMA:
                errors.append(f"pooled MLP checkpoint schema mismatch {name}")
            if checkpoint.get("contract") != baseline_manifest.get("contract"):
                errors.append(f"pooled MLP checkpoint contract mismatch {name}")
            checkpoint_audit[name] = {
                "epoch": checkpoint.get("epoch"),
                "best_epoch": checkpoint.get("best_epoch"),
                "sha256": sha256_file(baseline_dir / name),
            }
    except Exception as exc:  # noqa: BLE001 - surface checkpoint audit failure.
        errors.append(f"checkpoint inspection failed: {type(exc).__name__}: {exc}")

    report = {
        "schema_ver": "engineering-smoke-artifact-audit.stage7.v1",
        "checked_at": now_iso(),
        "status": "ok" if not errors else "error",
        "baseline_run_id": baseline_manifest.get("run_id"),
        "graphsage_run_id": graph_manifest.get("run_id"),
        "prediction_count": len(predictions),
        "prediction_splits": sorted(str(value) for value in prediction_splits),
        "comparison": baseline_metrics.get("comparison"),
        "graphsage_best_epoch": graph_metrics.get("best_epoch"),
        "pooled_mlp_best_epoch": baseline_metrics.get("pooled_mlp", {}).get("best_epoch"),
        "inference_graphs_checked": consistency.get("graphs_checked"),
        "max_batch_single_difference": consistency.get("max_batch_single_difference"),
        "max_single_stored_difference": consistency.get("max_single_stored_difference"),
        "held_out_graph_files_loaded": 0,
        "held_out_predictions": 0,
        "checkpoint_audit": checkpoint_audit,
        "errors": errors,
    }
    write_json(path_within_root(root, args.out), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
