#!/usr/bin/env python3
"""Train pooled-feature MLP and compare it with rule and GraphSAGE baselines."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphsage_model import FEATURE_DIM, graph_tensors, require_torch_stack
from graphsage_train import (
    TRAINING_SPLITS,
    binary_metrics,
    build_loss,
    cpu_state_dict,
    is_improvement,
    load_allowed_splits,
    minibatches,
    path_within_root,
    read_json,
    safe_run_id,
    validate_split_manifest,
    write_json,
)
from rule_baseline_scorer import evaluate_graph
from training_runtime import (
    canonical_hash,
    capture_rng_state,
    git_commit,
    installed_version,
    seed_everything,
    select_device,
    sha256_file,
)


POOLED_FEATURE_DIM = FEATURE_DIM * 2 + 4
CHECKPOINT_SCHEMA = "pooled-mlp-checkpoint.stage7.v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def validate_config(config: Any) -> None:
    if not isinstance(config, dict) or config.get("schema_ver") != "engineering-smoke.stage7.v1":
        raise ValueError("unsupported Stage 7 configuration")
    if config.get("training_scope") != "engineering_smoke_only":
        raise ValueError("Stage 7 configuration must remain engineering_smoke_only")
    if config.get("held_out_test_policy") != "prohibited_until_model_and_threshold_freeze":
        raise ValueError("held-out test policy is not strict enough")
    mlp = config.get("pooled_mlp", {})
    positive = ("batch_size", "hidden_dim", "lr", "epochs", "patience", "gradient_clip")
    if any(float(mlp.get(name, 0)) <= 0 for name in positive):
        raise ValueError("pooled MLP positive hyperparameter is invalid")
    if not 0 <= float(mlp.get("dropout", -1)) < 1:
        raise ValueError("pooled MLP dropout must be in [0, 1)")
    if mlp.get("monitor") != "pr_auc":
        raise ValueError("Stage 7 model selection must monitor validation PR-AUC")


def pooled_feature(torch: Any, graph: dict[str, Any]) -> Any:
    """Pool node/incident features without using message-passing adjacency."""
    x, _, _ = graph_tensors([graph])
    readout_mask = (x[:, 1] + x[:, 3]) > 0
    selected = x[readout_mask] if bool(readout_mask.any()) else x
    mean = selected.mean(dim=0)
    maximum = selected.max(dim=0).values
    nodes = max(len(graph.get("nodes", [])), 1)
    edges = max(len(graph.get("edges", [])), 1)
    address_count = sum(
        isinstance(node, dict) and node.get("node_type") == "address"
        for node in graph.get("nodes", [])
    )
    protocol_count = sum(
        isinstance(node, dict) and node.get("node_type") == "protocol"
        for node in graph.get("nodes", [])
    )
    structural = torch.tensor(
        [
            min(math.log1p(nodes) / 10.0, 1.0),
            min(math.log1p(edges) / 10.0, 1.0),
            address_count / nodes,
            protocol_count / nodes,
        ],
        dtype=torch.float32,
    )
    result = torch.cat((mean, maximum, structural))
    if result.numel() != POOLED_FEATURE_DIM or not bool(torch.isfinite(result).all()):
        raise ValueError("pooled feature contract failed")
    return result


def attach_features(torch: Any, records: dict[str, list[dict[str, Any]]]) -> str:
    hash_records: list[dict[str, Any]] = []
    for split in TRAINING_SPLITS:
        for sample in records[split]:
            feature = pooled_feature(torch, sample["graph"])
            sample["pooled_feature"] = feature
            hash_records.append(
                {
                    "split": split,
                    "tx_hash": sample["metadata"]["tx_hash"],
                    "feature": [round(float(value), 10) for value in feature.tolist()],
                }
            )
    return canonical_hash(hash_records)


def feature_batch(torch: Any, samples: list[dict[str, Any]], device: Any) -> tuple[Any, Any]:
    features = torch.stack([sample["pooled_feature"] for sample in samples]).to(device)
    target = torch.tensor(
        [sample["metadata"]["label"] for sample in samples], dtype=torch.float32
    ).to(device)
    return features, target


def evaluate_mlp(
    torch: Any,
    model: Any,
    samples: list[dict[str, Any]],
    batch_size: int,
    device: Any,
    loss_function: Any,
    threshold: float,
) -> tuple[dict[str, float], list[float]]:
    model.eval()
    labels: list[int] = []
    scores: list[float] = []
    total_loss = 0.0
    with torch.no_grad():
        for sample_batch in minibatches(samples, batch_size):
            features, target = feature_batch(torch, sample_batch, device)
            logits = model(features).squeeze(-1)
            loss = loss_function(logits, target)
            total_loss += float(loss.detach().cpu().item()) * len(sample_batch)
            scores.extend(float(value) for value in torch.sigmoid(logits).cpu().tolist())
            labels.extend(int(sample["metadata"]["label"]) for sample in sample_batch)
    metrics = binary_metrics(labels, scores, threshold)
    metrics["loss"] = total_loss / len(samples)
    return metrics, scores


def evaluate_rules(
    records: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
    threshold: float,
) -> tuple[dict[str, dict[str, float]], dict[str, list[float]], dict[str, list[list[str]]]]:
    metrics: dict[str, dict[str, float]] = {}
    scores: dict[str, list[float]] = {}
    reasons: dict[str, list[list[str]]] = {}
    for split in TRAINING_SPLITS:
        labels = [int(sample["metadata"]["label"]) for sample in records[split]]
        split_scores: list[float] = []
        split_reasons: list[list[str]] = []
        for sample in records[split]:
            score, reason_codes, _ = evaluate_graph(sample["graph"], config)
            split_scores.append(float(score))
            split_reasons.append(reason_codes)
        scores[split] = split_scores
        reasons[split] = split_reasons
        metrics[split] = binary_metrics(labels, split_scores, threshold)
    return metrics, scores, reasons


def graph_prediction_map(root: Path, run_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    path = root / run_manifest["outputs"]["predictions"]
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            tx_hash = item["tx_hash"]
            if tx_hash in result:
                raise ValueError(f"duplicate GraphSAGE prediction {tx_hash}")
            result[tx_hash] = item
    return result


def validate_graphsage_run(
    root: Path,
    run_dir: Path,
    split_manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    run_manifest = read_json(run_dir / "run_manifest.json")
    metrics = read_json(run_dir / "metrics.json")
    if run_manifest.get("schema_ver") != "graphsage-run-manifest.stage6.v1":
        raise ValueError("GraphSAGE run manifest schema mismatch")
    contract = run_manifest.get("contract", {})
    for key in ("split_content_hash", "graph_data_hash", "label_content_hash"):
        if contract.get(key) != split_manifest.get(key):
            raise ValueError(f"GraphSAGE contract mismatch: {key}")
    held_out = run_manifest.get("held_out_test", {})
    if held_out.get("graph_files_loaded") != 0 or held_out.get("predictions") != 0:
        raise ValueError("GraphSAGE run touched held-out test data")
    predictions = graph_prediction_map(root, run_manifest)
    return run_manifest, metrics, predictions


def dependency_versions() -> dict[str, str | None]:
    return {
        name: installed_version(name)
        for name in ("torch", "torch-geometric", "numpy")
    }


def checkpoint_payload(
    torch: Any,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    epoch: int,
    best_epoch: int,
    best_metric: float,
    best_state: dict[str, Any],
    history: list[dict[str, Any]],
    contract: dict[str, Any],
    model_config: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    return {
        "schema_ver": CHECKPOINT_SCHEMA,
        "saved_at": now_iso(),
        "run_id": run_id,
        "epoch": epoch,
        "best_epoch": best_epoch,
        "best_metric": best_metric,
        "model_config": model_config,
        "state_dict": cpu_state_dict(model),
        "best_model_state_dict": best_state,
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
        "rng_state": capture_rng_state(torch),
        "history": history,
        "contract": contract,
    }


def save_checkpoint(torch: Any, path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def write_predictions(
    path: Path,
    records: dict[str, list[dict[str, Any]]],
    graph_predictions: dict[str, dict[str, Any]],
    mlp_scores: dict[str, list[float]],
    rule_scores: dict[str, list[float]],
    rule_reasons: dict[str, list[list[str]]],
    threshold: float,
) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for split in TRAINING_SPLITS:
            for index, sample in enumerate(records[split]):
                metadata = sample["metadata"]
                tx_hash = metadata["tx_hash"]
                graph_prediction = graph_predictions.get(tx_hash)
                if graph_prediction is None or graph_prediction.get("split") != split:
                    raise ValueError(f"missing GraphSAGE prediction {tx_hash}")
                payload = {
                    "schema_ver": "engineering-smoke-prediction.stage7.v1",
                    "split": split,
                    "tx_hash": tx_hash,
                    "group_id": metadata["group_id"],
                    "incident_id": metadata.get("incident_id"),
                    "label": metadata["label"],
                    "threshold": threshold,
                    "scores": {
                        "rule_baseline": rule_scores[split][index],
                        "pooled_feature_mlp": round(mlp_scores[split][index], 10),
                        "graphsage": graph_prediction["probability"],
                    },
                    "rule_reasons": rule_reasons[split][index],
                }
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
                count += 1
    return count


def comparison_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for model_name, model_metrics in metrics.items():
        validation = model_metrics["validation"]
        rows.append(
            {
                "model": model_name,
                "validation_pr_auc": validation["pr_auc"],
                "validation_roc_auc": validation["roc_auc"],
                "validation_precision": validation["precision"],
                "validation_recall": validation["recall"],
                "validation_f1": validation["f1"],
                "validation_brier_score": validation["brier_score"],
            }
        )
    return sorted(rows, key=lambda row: (-row["validation_pr_auc"], row["model"]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 7 engineering smoke baselines.")
    parser.add_argument("--config", default="config/engineering_smoke.stage7.v1.json")
    parser.add_argument("--graphsage-run-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", default="models/graphsage/runs")
    parser.add_argument("--report", default="ops/reports/engineering-smoke.stage7.latest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path.cwd().resolve()
    config_path = path_within_root(root, args.config)
    config = read_json(config_path)
    validate_config(config)
    split_path = path_within_root(root, config["split_manifest"])
    split_manifest = read_json(split_path)
    split_audit = validate_split_manifest(split_manifest)
    records, load_audit = load_allowed_splits(root, split_manifest)
    graph_run_dir = path_within_root(root, args.graphsage_run_dir)
    graph_run_manifest, graph_metrics, graph_predictions = validate_graphsage_run(
        root, graph_run_dir, split_manifest
    )

    run_id = safe_run_id(args.run_id)
    output_root = path_within_root(root, args.output_root)
    run_dir = output_root / run_id
    if run_dir.exists():
        raise ValueError(f"run directory already exists: {run_dir.relative_to(root)}")
    run_dir.mkdir(parents=True)
    report_path = path_within_root(root, args.report)

    torch, nn, functional, _ = require_torch_stack()
    device, device_audit = select_device(torch, config["device"])
    reproducibility = seed_everything(torch, int(config["seed"]))
    feature_hash = attach_features(torch, records)
    mlp_config = dict(config["pooled_mlp"])
    model_config = {
        "input_dim": POOLED_FEATURE_DIM,
        "hidden_dim": int(mlp_config["hidden_dim"]),
        "dropout": float(mlp_config["dropout"]),
        "architecture": "Linear-ReLU-Dropout-Linear",
        "feature_pooling": "address_protocol_mean_max_plus_four_structural",
    }

    class PooledFeatureMLP(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.network = nn.Sequential(
                nn.Linear(model_config["input_dim"], model_config["hidden_dim"]),
                nn.ReLU(),
                nn.Dropout(model_config["dropout"]),
                nn.Linear(model_config["hidden_dim"], 1),
            )

        def forward(self, features: Any) -> Any:
            return self.network(features)

    train_samples = records["train"]
    positive_count = sum(sample["metadata"]["label"] for sample in train_samples)
    negative_count = len(train_samples) - positive_count
    loss_function = build_loss(
        torch,
        functional,
        mlp_config["loss"],
        positive_count,
        negative_count,
        float(mlp_config["focal_gamma"]),
    )
    model = PooledFeatureMLP().to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(mlp_config["lr"]),
        weight_decay=float(mlp_config["weight_decay"]),
        betas=(0.9, 0.95),
        eps=1e-10,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=int(mlp_config["epochs"]),
        eta_min=float(mlp_config["lr"]) * 0.1,
    )
    contract = {
        "split_manifest_sha256": sha256_file(split_path),
        "split_content_hash": split_manifest["split_content_hash"],
        "graph_data_hash": split_manifest["graph_data_hash"],
        "label_content_hash": split_manifest["label_content_hash"],
        "feature_version": split_manifest["feature_version"],
        "label_version": split_manifest["label_version"],
        "pooled_feature_hash": feature_hash,
        "config_sha256": sha256_file(config_path),
        "training_scope": config["training_scope"],
    }

    best_path = run_dir / "best_model.pt"
    last_path = run_dir / "last_model.pt"
    metrics_path = run_dir / "metrics.json"
    predictions_path = run_dir / "predictions.jsonl"
    curves_path = run_dir / "curves.json"
    manifest_path = run_dir / "run_manifest.json"
    best_metric = -math.inf
    best_epoch = 0
    best_state = cpu_state_dict(model)
    history: list[dict[str, Any]] = []
    stale_epochs = 0
    stopped_early = False
    last_epoch = 0
    started_at = now_iso()
    started = time.monotonic()

    for epoch in range(1, int(mlp_config["epochs"]) + 1):
        last_epoch = epoch
        model.train()
        loss_total = 0.0
        gradient_norms: list[float] = []
        learning_rate = float(optimizer.param_groups[0]["lr"])
        for sample_batch in minibatches(
            train_samples, int(mlp_config["batch_size"]), int(config["seed"]) + epoch
        ):
            features, target = feature_batch(torch, sample_batch, device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(features).squeeze(-1)
            loss = loss_function(logits, target)
            if not bool(torch.isfinite(loss).item()):
                raise RuntimeError(f"non-finite pooled MLP loss at epoch {epoch}")
            loss.backward()
            gradient_norm = float(
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), float(mlp_config["gradient_clip"])
                )
                .detach()
                .cpu()
                .item()
            )
            if not math.isfinite(gradient_norm):
                raise RuntimeError(f"non-finite pooled MLP gradient at epoch {epoch}")
            optimizer.step()
            loss_total += float(loss.detach().cpu().item()) * len(sample_batch)
            gradient_norms.append(gradient_norm)

        validation_metrics, _ = evaluate_mlp(
            torch,
            model,
            records["validation"],
            int(mlp_config["batch_size"]),
            device,
            loss_function,
            float(config["threshold"]),
        )
        value = validation_metrics["pr_auc"]
        improved = is_improvement(value, best_metric, "pr_auc")
        if improved:
            best_metric = value
            best_epoch = epoch
            best_state = cpu_state_dict(model)
            stale_epochs = 0
        else:
            stale_epochs += 1
        scheduler.step()
        history.append(
            {
                "epoch": epoch,
                "train_loss": loss_total / len(train_samples),
                "validation_loss": validation_metrics["loss"],
                "validation_pr_auc": validation_metrics["pr_auc"],
                "validation_roc_auc": validation_metrics["roc_auc"],
                "learning_rate": learning_rate,
                "next_learning_rate": float(optimizer.param_groups[0]["lr"]),
                "gradient_norm_mean": sum(gradient_norms) / len(gradient_norms),
                "gradient_norm_max": max(gradient_norms),
            }
        )
        checkpoint = checkpoint_payload(
            torch,
            model,
            optimizer,
            scheduler,
            epoch,
            best_epoch,
            best_metric,
            best_state,
            history,
            contract,
            model_config,
            run_id,
        )
        save_checkpoint(torch, last_path, checkpoint)
        if improved:
            best_checkpoint = dict(checkpoint)
            best_checkpoint["state_dict"] = best_state
            save_checkpoint(torch, best_path, best_checkpoint)
        if stale_epochs >= int(mlp_config["patience"]):
            stopped_early = True
            break

    model.load_state_dict(best_state)
    mlp_metrics: dict[str, dict[str, float]] = {}
    mlp_scores: dict[str, list[float]] = {}
    for split in TRAINING_SPLITS:
        metrics, scores = evaluate_mlp(
            torch,
            model,
            records[split],
            int(mlp_config["batch_size"]),
            device,
            loss_function,
            float(config["threshold"]),
        )
        mlp_metrics[split] = metrics
        mlp_scores[split] = scores

    rule_config_path = path_within_root(root, config["rule_baseline_config"])
    rule_config = read_json(rule_config_path)
    rule_metrics, rule_scores, rule_reasons = evaluate_rules(
        records, rule_config, float(config["threshold"])
    )
    model_metrics = {
        "rule_baseline": rule_metrics,
        "pooled_feature_mlp": mlp_metrics,
        "graphsage": graph_metrics["best_model_metrics"],
    }
    rows = comparison_rows(model_metrics)
    predictions_written = write_predictions(
        predictions_path,
        records,
        graph_predictions,
        mlp_scores,
        rule_scores,
        rule_reasons,
        float(config["threshold"]),
    )
    metrics_payload = {
        "schema_ver": "engineering-smoke-metrics.stage7.v1",
        "training_scope": config["training_scope"],
        "run_id": run_id,
        "threshold": config["threshold"],
        "models": model_metrics,
        "comparison": rows,
        "pooled_mlp": {
            "best_epoch": best_epoch,
            "last_epoch": last_epoch,
            "best_validation_pr_auc": best_metric,
            "stopped_early": stopped_early,
        },
        "held_out_test": {"evaluated": False, "graph_files_loaded": 0, "predictions": 0},
    }
    write_json(metrics_path, metrics_payload)
    write_json(curves_path, {"schema_ver": "pooled-mlp-curves.stage7.v1", "epochs": history})

    relative_outputs = {
        "best_model": str(best_path.relative_to(root)),
        "last_model": str(last_path.relative_to(root)),
        "metrics": str(metrics_path.relative_to(root)),
        "predictions": str(predictions_path.relative_to(root)),
        "curves": str(curves_path.relative_to(root)),
    }
    output_hashes = {name: sha256_file(root / path) for name, path in relative_outputs.items()}
    run_manifest = {
        "schema_ver": "engineering-smoke-run-manifest.stage7.v1",
        "status": "ok",
        "run_id": run_id,
        "created_at": started_at,
        "completed_at": now_iso(),
        "duration_seconds": time.monotonic() - started,
        "git_commit": git_commit(root),
        "command": ["python", "scripts/engineering_smoke_baselines.py", *sys.argv[1:]],
        "contract": contract,
        "split_audit": split_audit,
        "load_audit": load_audit,
        "model_config": model_config,
        "optimization": mlp_config,
        "seed": config["seed"],
        "reproducibility": reproducibility,
        "dependencies": dependency_versions(),
        "device": device_audit,
        "rule_baseline": {
            "config": str(rule_config_path.relative_to(root)),
            "config_sha256": sha256_file(rule_config_path),
        },
        "graphsage_run": {
            "run_id": graph_run_manifest["run_id"],
            "run_manifest": str((graph_run_dir / "run_manifest.json").relative_to(root)),
            "run_manifest_sha256": sha256_file(graph_run_dir / "run_manifest.json"),
            "best_model_sha256": graph_run_manifest["output_sha256"]["best_model"],
        },
        "result": {
            "pooled_mlp_best_epoch": best_epoch,
            "pooled_mlp_last_epoch": last_epoch,
            "pooled_mlp_stopped_early": stopped_early,
            "comparison": rows,
        },
        "held_out_test": {
            "manifest_items": split_audit["item_counts"]["held_out_test"],
            "graph_files_loaded": 0,
            "predictions": 0,
            "evaluated": False,
        },
        "outputs": relative_outputs,
        "output_sha256": output_hashes,
        "predictions_written": predictions_written,
    }
    write_json(manifest_path, run_manifest)

    report = {
        "schema_ver": "engineering-smoke-report.stage7.v1",
        "checked_at": now_iso(),
        "status": "ok",
        "training_scope": config["training_scope"],
        "run_id": run_id,
        "run_manifest": str(manifest_path.relative_to(root)),
        "run_manifest_sha256": sha256_file(manifest_path),
        "graphsage_run_id": graph_run_manifest["run_id"],
        "comparison": rows,
        "train_graph_files_loaded": load_audit["graph_files_loaded_by_split"]["train"],
        "validation_graph_files_loaded": load_audit["graph_files_loaded_by_split"]["validation"],
        "held_out_graph_files_loaded": 0,
        "held_out_predictions": 0,
        "predictions_written": predictions_written,
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
