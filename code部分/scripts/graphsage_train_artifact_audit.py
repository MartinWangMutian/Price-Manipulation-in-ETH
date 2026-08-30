#!/usr/bin/env python3
"""Audit Stage 6 trainer outputs and prove the held-out split stayed untouched."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphsage_train import CHECKPOINT_SCHEMA, TRAINING_SPLITS, read_json, write_json
from training_runtime import sha256_file


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a completed Stage 6 GraphSAGE run.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--split-manifest", default="data/training/split_manifest.stage4.v1.json"
    )
    parser.add_argument("--require-resume", action="store_true")
    parser.add_argument("--out", default="ops/reports/graphsage-train-artifact-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd().resolve()
    run_dir = (root / args.run_dir).resolve()
    split_manifest = read_json(root / args.split_manifest)
    errors: list[str] = []
    required_names = (
        "best_model.pt",
        "last_model.pt",
        "metrics.json",
        "predictions.jsonl",
        "run_manifest.json",
        "curves.json",
        "curves.csv",
    )
    for name in required_names:
        if not (run_dir / name).is_file():
            errors.append(f"missing artifact {name}")

    run_manifest: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    predictions: list[dict[str, Any]] = []
    checkpoint_audit: dict[str, Any] = {}
    if not errors:
        run_manifest = read_json(run_dir / "run_manifest.json")
        metrics = read_json(run_dir / "metrics.json")
        with (run_dir / "predictions.jsonl").open("r", encoding="utf-8") as handle:
            predictions = [json.loads(line) for line in handle if line.strip()]

        if run_manifest.get("schema_ver") != "graphsage-run-manifest.stage6.v1":
            errors.append("run manifest schema mismatch")
        if metrics.get("schema_ver") != "graphsage-metrics.stage6.v1":
            errors.append("metrics schema mismatch")
        if run_manifest.get("status") != "ok":
            errors.append("run manifest status is not ok")

        expected_contract = {
            "split_content_hash": split_manifest["split_content_hash"],
            "graph_data_hash": split_manifest["graph_data_hash"],
            "label_content_hash": split_manifest["label_content_hash"],
            "feature_version": split_manifest["feature_version"],
            "label_version": split_manifest["label_version"],
        }
        observed_contract = run_manifest.get("contract", {})
        for key, value in expected_contract.items():
            if observed_contract.get(key) != value:
                errors.append(f"contract mismatch {key}")

        outputs = run_manifest.get("outputs", {})
        hashes = run_manifest.get("output_sha256", {})
        for name, path_value in outputs.items():
            path = root / path_value
            if not path.is_file():
                errors.append(f"manifest output missing {name}")
            elif sha256_file(path) != hashes.get(name):
                errors.append(f"manifest output hash mismatch {name}")

        allowed_items = [
            item for item in split_manifest["items"] if item["split"] in TRAINING_SPLITS
        ]
        expected_transactions = {item["tx_hash"] for item in allowed_items}
        predicted_transactions = {item.get("tx_hash") for item in predictions}
        prediction_splits = {item.get("split") for item in predictions}
        if predicted_transactions != expected_transactions:
            errors.append("prediction transaction set does not equal train+validation")
        if not prediction_splits.issubset(set(TRAINING_SPLITS)):
            errors.append("predictions contain a forbidden split")
        if len(predictions) != len(expected_transactions):
            errors.append("prediction count mismatch")

        held_out_claims = (
            run_manifest.get("held_out_test", {}),
            metrics.get("held_out_test", {}),
        )
        for claim in held_out_claims:
            if claim.get("graph_files_loaded") != 0 or claim.get("predictions") != 0:
                errors.append("held-out isolation claim is not zero")
            if claim.get("evaluated") is not False:
                errors.append("held-out split was marked evaluated")
        if run_manifest.get("load_audit", {}).get("held_out_graph_files_loaded") != 0:
            errors.append("load audit reports held-out graph access")

        if args.require_resume:
            resume = run_manifest.get("resume", {})
            if not resume.get("resumed_from") or int(resume.get("start_epoch", 0)) <= 1:
                errors.append("resume evidence is missing")

        try:
            import torch

            for name in ("best_model.pt", "last_model.pt"):
                checkpoint = torch.load(
                    run_dir / name, map_location="cpu", weights_only=False
                )
                if checkpoint.get("schema_ver") != CHECKPOINT_SCHEMA:
                    errors.append(f"checkpoint schema mismatch {name}")
                if checkpoint.get("contract") != observed_contract:
                    errors.append(f"checkpoint contract mismatch {name}")
                checkpoint_audit[name] = {
                    "epoch": checkpoint.get("epoch"),
                    "best_epoch": checkpoint.get("best_epoch"),
                    "sha256": sha256_file(run_dir / name),
                }
        except Exception as exc:  # noqa: BLE001 - convert inspection failures to audit errors.
            errors.append(f"checkpoint inspection failed: {type(exc).__name__}: {exc}")

    report = {
        "schema_ver": "graphsage-train-artifact-audit.stage6.v1",
        "checked_at": now_iso(),
        "status": "ok" if not errors else "error",
        "run_dir": relative(root, run_dir),
        "run_id": run_manifest.get("run_id"),
        "required_artifacts": list(required_names),
        "prediction_count": len(predictions),
        "prediction_splits": sorted(
            str(value) for value in {item.get("split") for item in predictions}
        ),
        "held_out_graph_files_loaded": run_manifest.get("held_out_test", {}).get(
            "graph_files_loaded"
        ),
        "held_out_predictions": run_manifest.get("held_out_test", {}).get("predictions"),
        "checkpoint_audit": checkpoint_audit,
        "resume_required": args.require_resume,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
