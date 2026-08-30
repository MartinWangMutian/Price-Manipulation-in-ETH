#!/usr/bin/env python3
"""Compare GraphSAGE best-checkpoint batch, single-graph, and stored predictions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphsage_model import CashFlowGraphSAGE, GraphSAGEConfig, graph_tensors, require_torch_stack
from graphsage_train import (
    TRAINING_SPLITS,
    load_allowed_splits,
    path_within_root,
    read_json,
    validate_split_manifest,
    write_json,
)
from training_runtime import select_device, sha256_file


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def max_absolute_difference(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("prediction vectors have different lengths")
    return max((abs(a - b) for a, b in zip(left, right)), default=0.0)


def stored_predictions(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            tx_hash = item["tx_hash"]
            if tx_hash in result:
                raise ValueError(f"duplicate stored prediction {tx_hash}")
            result[tx_hash] = item
    return result


def score_graphs(torch: Any, model: Any, graphs: list[dict[str, Any]], device: Any) -> list[float]:
    x, edge_index, batch = graph_tensors(graphs)
    with torch.no_grad():
        probabilities = model(x.to(device), edge_index.to(device), batch.to(device))
    return [float(value) for value in probabilities.detach().cpu().tolist()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit GraphSAGE inference consistency.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--split-manifest", default="data/training/split_manifest.stage4.v1.json"
    )
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument(
        "--out", default="ops/reports/graphsage-inference-consistency.stage7.latest.json"
    )
    args = parser.parse_args()
    if args.tolerance <= 0:
        raise ValueError("tolerance must be positive")

    root = Path.cwd().resolve()
    run_dir = path_within_root(root, args.run_dir)
    split_path = path_within_root(root, args.split_manifest)
    split_manifest = read_json(split_path)
    split_audit = validate_split_manifest(split_manifest)
    records, load_audit = load_allowed_splits(root, split_manifest)
    run_manifest = read_json(run_dir / "run_manifest.json")
    if run_manifest.get("schema_ver") != "graphsage-run-manifest.stage6.v1":
        raise ValueError("unsupported GraphSAGE run manifest")
    for key in ("split_content_hash", "graph_data_hash", "label_content_hash"):
        if run_manifest.get("contract", {}).get(key) != split_manifest.get(key):
            raise ValueError(f"GraphSAGE run contract mismatch: {key}")
    held_out = run_manifest.get("held_out_test", {})
    if held_out.get("graph_files_loaded") != 0 or held_out.get("predictions") != 0:
        raise ValueError("GraphSAGE run touched held-out test data")

    torch, _, _, _ = require_torch_stack()
    device, device_audit = select_device(torch, args.device)
    config = GraphSAGEConfig(**run_manifest["model_config"])
    model = CashFlowGraphSAGE(config).to(device)
    best_path = root / run_manifest["outputs"]["best_model"]
    if sha256_file(best_path) != run_manifest["output_sha256"]["best_model"]:
        raise ValueError("best checkpoint hash mismatch")
    checkpoint = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    prediction_path = root / run_manifest["outputs"]["predictions"]
    stored = stored_predictions(prediction_path)

    items: list[dict[str, Any]] = []
    max_batch_single = 0.0
    max_single_stored = 0.0
    for split in TRAINING_SPLITS:
        split_records = records[split]
        batch_scores = score_graphs(
            torch, model, [sample["graph"] for sample in split_records], device
        )
        single_scores = [
            score_graphs(torch, model, [sample["graph"]], device)[0]
            for sample in split_records
        ]
        max_batch_single = max(
            max_batch_single, max_absolute_difference(batch_scores, single_scores)
        )
        stored_scores = []
        for sample in split_records:
            tx_hash = sample["metadata"]["tx_hash"]
            prediction = stored.get(tx_hash)
            if prediction is None or prediction.get("split") != split:
                raise ValueError(f"missing stored prediction {tx_hash}")
            stored_scores.append(float(prediction["probability"]))
        max_single_stored = max(
            max_single_stored, max_absolute_difference(single_scores, stored_scores)
        )
        for sample, batch_score, single_score, stored_score in zip(
            split_records, batch_scores, single_scores, stored_scores
        ):
            items.append(
                {
                    "split": split,
                    "tx_hash": sample["metadata"]["tx_hash"],
                    "batch_probability": batch_score,
                    "single_probability": single_score,
                    "stored_probability": stored_score,
                    "batch_single_difference": abs(batch_score - single_score),
                    "single_stored_difference": abs(single_score - stored_score),
                }
            )

    expected_transactions = {
        sample["metadata"]["tx_hash"]
        for split in TRAINING_SPLITS
        for sample in records[split]
    }
    errors: list[str] = []
    if set(stored) != expected_transactions:
        errors.append("stored prediction set does not equal train+validation")
    if max_batch_single > args.tolerance:
        errors.append("batch versus single inference exceeds tolerance")
    if max_single_stored > args.tolerance:
        errors.append("single versus stored inference exceeds tolerance")

    report = {
        "schema_ver": "graphsage-inference-consistency.stage7.v1",
        "checked_at": now_iso(),
        "status": "ok" if not errors else "error",
        "run_id": run_manifest["run_id"],
        "run_dir": str(run_dir.relative_to(root)),
        "checkpoint": str(best_path.relative_to(root)),
        "checkpoint_sha256": sha256_file(best_path),
        "device": device_audit,
        "tolerance": args.tolerance,
        "graphs_checked": len(items),
        "split_counts": {
            split: len(records[split]) for split in TRAINING_SPLITS
        },
        "max_batch_single_difference": max_batch_single,
        "max_single_stored_difference": max_single_stored,
        "split_audit": split_audit,
        "load_audit": load_audit,
        "held_out_graph_files_loaded": 0,
        "held_out_predictions": 0,
        "errors": errors,
        "items": items,
    }
    out_path = path_within_root(root, args.out)
    write_json(out_path, report)
    print(json.dumps({key: value for key, value in report.items() if key != "items"}, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
