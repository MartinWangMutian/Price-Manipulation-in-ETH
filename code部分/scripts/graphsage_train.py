#!/usr/bin/env python3
"""Leakage-safe, reproducible GraphSAGE trainer for frozen split manifests."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from graphsage_model import (
    CashFlowGraphSAGE,
    FEATURE_DIM,
    GraphSAGEConfig,
    graph_tensors,
    require_torch_stack,
)
from training_runtime import (
    canonical_hash,
    capture_rng_state,
    git_commit,
    installed_version,
    restore_rng_state,
    seed_everything,
    select_device,
    sha256_file,
)


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
TRAINING_SPLITS = ("train", "validation")
CHECKPOINT_SCHEMA = "graphsage-checkpoint.stage6.v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_run_id(value: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "run_id must start with an alphanumeric character and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )
    return value


def path_within_root(root: Path, value: str | Path) -> Path:
    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes project root: {value}")
    return candidate


def validate_split_manifest(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("split manifest must be a JSON object")
    if payload.get("schema_ver") != "grouped-split-manifest.stage4.v1":
        raise ValueError("unsupported split manifest schema")
    if payload.get("frozen") is not True:
        raise ValueError("split manifest must be frozen before training")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("split manifest has no items")

    seen_transactions: set[str] = set()
    groups_by_split: dict[str, set[str]] = {
        "train": set(),
        "validation": set(),
        "held_out_test": set(),
    }
    counts: dict[str, dict[int, int]] = {
        split: {0: 0, 1: 0} for split in groups_by_split
    }
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("split manifest item must be an object")
        split = item.get("split")
        label = item.get("label")
        tx_hash = str(item.get("tx_hash", "")).lower()
        group_id = item.get("group_id")
        if split not in groups_by_split:
            raise ValueError(f"unsupported split {split!r}")
        if label not in {0, 1}:
            raise ValueError(f"invalid label for {tx_hash or '<missing tx_hash>'}")
        if not tx_hash or tx_hash in seen_transactions:
            raise ValueError(f"duplicate or missing transaction {tx_hash!r}")
        if not isinstance(group_id, str) or not group_id:
            raise ValueError(f"missing group_id for {tx_hash}")
        seen_transactions.add(tx_hash)
        groups_by_split[split].add(group_id)
        counts[split][int(label)] += 1

    split_names = tuple(groups_by_split)
    for left_index, left in enumerate(split_names):
        for right in split_names[left_index + 1 :]:
            overlap = groups_by_split[left] & groups_by_split[right]
            if overlap:
                raise ValueError(f"group leakage between {left} and {right}: {sorted(overlap)}")
    for split in TRAINING_SPLITS:
        if not all(counts[split].values()):
            raise ValueError(f"{split} must contain both positive and negative labels")

    return {
        "item_counts": {split: sum(values.values()) for split, values in counts.items()},
        "label_counts": {
            split: {str(label): count for label, count in values.items()}
            for split, values in counts.items()
        },
        "group_counts": {split: len(groups) for split, groups in groups_by_split.items()},
    }


def load_allowed_splits(
    root: Path, manifest: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Load train/validation graphs without opening any held-out graph path."""
    records: dict[str, list[dict[str, Any]]] = {split: [] for split in TRAINING_SPLITS}
    loaded_paths: list[str] = []
    for item in manifest["items"]:
        split = item["split"]
        if split not in TRAINING_SPLITS:
            continue
        graph_path = path_within_root(root, item["graph_ref"])
        if not graph_path.is_file():
            raise ValueError(f"graph_ref is missing: {item['graph_ref']}")
        observed_hash = sha256_file(graph_path)
        if observed_hash != item.get("graph_sha256"):
            raise ValueError(f"graph hash mismatch: {item['graph_ref']}")
        graph = read_json(graph_path)
        if graph.get("schema_ver") != "graph-inference.v1":
            raise ValueError(f"unsupported graph schema: {item['graph_ref']}")
        if str(graph.get("tx_hash", "")).lower() != str(item["tx_hash"]).lower():
            raise ValueError(f"graph transaction mismatch: {item['graph_ref']}")
        if graph.get("feature_ver") != manifest.get("feature_version"):
            raise ValueError(f"graph feature version mismatch: {item['graph_ref']}")
        records[split].append({"graph": graph, "metadata": dict(item)})
        loaded_paths.append(str(graph_path.relative_to(root)))

    for split in TRAINING_SPLITS:
        records[split].sort(key=lambda sample: sample["metadata"]["tx_hash"])
    return records, {
        "graph_files_loaded": len(loaded_paths),
        "graph_files_loaded_by_split": {
            split: len(records[split]) for split in TRAINING_SPLITS
        },
        "held_out_graph_files_loaded": 0,
        "loaded_path_hash": canonical_hash(loaded_paths),
    }


def minibatches(
    samples: list[dict[str, Any]], batch_size: int, seed: int | None = None
) -> Iterable[list[dict[str, Any]]]:
    indices = list(range(len(samples)))
    if seed is not None:
        random.Random(seed).shuffle(indices)
    for offset in range(0, len(indices), batch_size):
        yield [samples[index] for index in indices[offset : offset + batch_size]]


def pr_auc(labels: list[int], scores: list[float]) -> float:
    """Return tie-aware step-wise average precision (the PR-AUC selection metric)."""
    positives = sum(labels)
    if positives == 0:
        raise ValueError("PR-AUC requires at least one positive label")
    ranked = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    previous_recall = 0.0
    area = 0.0
    true_positives = 0
    false_positives = 0
    index = 0
    while index < len(ranked):
        score = ranked[index][0]
        while index < len(ranked) and ranked[index][0] == score:
            label = ranked[index][1]
            true_positives += int(label == 1)
            false_positives += int(label == 0)
            index += 1
        recall = true_positives / positives
        precision = true_positives / (true_positives + false_positives)
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return float(area)


def roc_auc(labels: list[int], scores: list[float]) -> float:
    positive_scores = [score for label, score in zip(labels, scores) if label == 1]
    negative_scores = [score for label, score in zip(labels, scores) if label == 0]
    if not positive_scores or not negative_scores:
        raise ValueError("ROC-AUC requires both classes")
    wins = 0.0
    for positive in positive_scores:
        for negative in negative_scores:
            wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(positive_scores) * len(negative_scores))


def binary_metrics(labels: list[int], scores: list[float], threshold: float) -> dict[str, float]:
    predictions = [int(score >= threshold) for score in scores]
    true_positive = sum(prediction == label == 1 for prediction, label in zip(predictions, labels))
    true_negative = sum(prediction == label == 0 for prediction, label in zip(predictions, labels))
    false_positive = sum(prediction == 1 and label == 0 for prediction, label in zip(predictions, labels))
    false_negative = sum(prediction == 0 and label == 1 for prediction, label in zip(predictions, labels))
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    return {
        "accuracy": (true_positive + true_negative) / len(labels),
        "precision": precision,
        "recall": recall,
        "f1": 2.0 * precision * recall / max(precision + recall, 1e-12),
        "pr_auc": pr_auc(labels, scores),
        "roc_auc": roc_auc(labels, scores),
        "brier_score": sum((score - label) ** 2 for label, score in zip(labels, scores))
        / len(labels),
        "true_positive": float(true_positive),
        "true_negative": float(true_negative),
        "false_positive": float(false_positive),
        "false_negative": float(false_negative),
    }


def build_loss(
    torch: Any,
    functional: Any,
    mode: str,
    positive_count: int,
    negative_count: int,
    focal_gamma: float,
) -> Any:
    positive_weight = negative_count / positive_count
    positive_alpha = negative_count / (positive_count + negative_count)
    negative_alpha = positive_count / (positive_count + negative_count)

    def calculate(logits: Any, target: Any) -> Any:
        if mode == "weighted_bce":
            pos_weight = logits.new_tensor([positive_weight])
            return functional.binary_cross_entropy_with_logits(
                logits, target, pos_weight=pos_weight
            )
        base = functional.binary_cross_entropy_with_logits(logits, target, reduction="none")
        probabilities = torch.sigmoid(logits)
        probability_of_target = torch.where(target == 1, probabilities, 1.0 - probabilities)
        alpha = torch.where(
            target == 1,
            logits.new_tensor(positive_alpha),
            logits.new_tensor(negative_alpha),
        )
        return (alpha * ((1.0 - probability_of_target) ** focal_gamma) * base).mean()

    return calculate


def batch_tensors(
    torch: Any, samples: list[dict[str, Any]], device: Any
) -> tuple[Any, Any, Any, Any]:
    x, edge_index, batch = graph_tensors([sample["graph"] for sample in samples])
    target = torch.tensor(
        [sample["metadata"]["label"] for sample in samples], dtype=torch.float32
    )
    return x.to(device), edge_index.to(device), batch.to(device), target.to(device)


def evaluate(
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
            x, edge_index, batch, target = batch_tensors(torch, sample_batch, device)
            logits = model.forward_logits(x, edge_index, batch)
            loss = loss_function(logits, target)
            total_loss += float(loss.detach().cpu().item()) * len(sample_batch)
            scores.extend(float(value) for value in torch.sigmoid(logits).detach().cpu().tolist())
            labels.extend(int(sample["metadata"]["label"]) for sample in sample_batch)
    metrics = binary_metrics(labels, scores, threshold)
    metrics["loss"] = total_loss / len(samples)
    return metrics, scores


def cpu_state_dict(model: Any) -> dict[str, Any]:
    return {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}


def checkpoint_payload(
    torch: Any,
    config: GraphSAGEConfig,
    model_state: dict[str, Any],
    optimizer: Any,
    scheduler: Any,
    epoch: int,
    best_epoch: int,
    best_metric: float,
    best_model_state: dict[str, Any],
    history: list[dict[str, Any]],
    contract: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    return {
        "schema_ver": CHECKPOINT_SCHEMA,
        "saved_at": now_iso(),
        "run_id": run_id,
        "epoch": epoch,
        "best_epoch": best_epoch,
        "best_metric": best_metric,
        "config": asdict(config),
        "state_dict": model_state,
        "best_model_state_dict": best_model_state,
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": scheduler.state_dict(),
        "history": history,
        "contract": contract,
        "rng_state": capture_rng_state(torch),
    }


def save_checkpoint(torch: Any, path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def load_resume_checkpoint(
    torch: Any,
    path: Path,
    device: Any,
    config: GraphSAGEConfig,
    contract: dict[str, Any],
) -> dict[str, Any]:
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    if checkpoint.get("schema_ver") != CHECKPOINT_SCHEMA:
        raise ValueError("resume checkpoint schema is not supported")
    if checkpoint.get("config") != asdict(config):
        raise ValueError("resume checkpoint model configuration mismatch")
    if checkpoint.get("contract") != contract:
        raise ValueError("resume checkpoint data/split contract mismatch")
    return checkpoint


def dependency_versions() -> dict[str, str | None]:
    return {
        name: installed_version(name)
        for name in ("torch", "torch-geometric", "numpy", "scipy")
    }


def write_predictions(
    path: Path,
    records: dict[str, list[dict[str, Any]]],
    scores: dict[str, list[float]],
    threshold: float,
) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for split in TRAINING_SPLITS:
            for sample, score in zip(records[split], scores[split]):
                metadata = sample["metadata"]
                payload = {
                    "schema_ver": "graphsage-prediction.stage6.v1",
                    "split": split,
                    "tx_hash": metadata["tx_hash"],
                    "graph_id": metadata["graph_id"],
                    "group_id": metadata["group_id"],
                    "incident_id": metadata.get("incident_id"),
                    "label": metadata["label"],
                    "probability": round(score, 10),
                    "prediction": int(score >= threshold),
                    "threshold": threshold,
                }
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
                count += 1
    return count


def write_curves(path_json: Path, path_csv: Path, history: list[dict[str, Any]]) -> None:
    write_json(path_json, {"schema_ver": "graphsage-curves.stage6.v1", "epochs": history})
    columns = (
        "epoch",
        "train_loss",
        "validation_loss",
        "validation_pr_auc",
        "validation_roc_auc",
        "learning_rate",
        "next_learning_rate",
        "gradient_norm_mean",
        "gradient_norm_max",
    )
    with path_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in history:
            writer.writerow({column: row[column] for column in columns})


def monitor_value(metrics: dict[str, float], monitor: str) -> float:
    return metrics["pr_auc"] if monitor == "pr_auc" else metrics["loss"]


def is_improvement(value: float, best: float, monitor: str, tolerance: float = 1e-12) -> bool:
    return value > best + tolerance if monitor == "pr_auc" else value < best - tolerance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train GraphSAGE from a frozen grouped split without touching held-out test graphs."
    )
    parser.add_argument(
        "--split-manifest", default="data/training/split_manifest.stage4.v1.json"
    )
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--resume")
    parser.add_argument("--run-id")
    parser.add_argument("--monitor", choices=("pr_auc", "validation_loss"), default="pr_auc")
    parser.add_argument("--loss", choices=("focal", "weighted_bce"), default="focal")
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--gradient-clip", type=float, default=1.0)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--model-version", default="graphsage.stage6.v1")
    parser.add_argument("--output-root", default="models/graphsage/runs")
    parser.add_argument("--report", default="ops/reports/graphsage-train.latest.json")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.batch_size < 1 or args.hidden_dim < 1 or args.num_layers < 1:
        raise ValueError("batch-size, hidden-dim, and num-layers must be positive")
    if args.epochs < 1 or args.patience < 1:
        raise ValueError("epochs and patience must be positive")
    if args.lr <= 0 or args.weight_decay < 0 or args.gradient_clip <= 0:
        raise ValueError("lr/gradient-clip must be positive and weight-decay non-negative")
    if not 0 <= args.dropout < 1 or not 0 <= args.threshold <= 1:
        raise ValueError("dropout must be in [0,1) and threshold in [0,1]")
    if args.focal_gamma < 0:
        raise ValueError("focal-gamma must be non-negative")


def main() -> int:
    args = parse_args()
    validate_args(args)
    root = Path.cwd().resolve()
    manifest_path = path_within_root(root, args.split_manifest)
    manifest = read_json(manifest_path)
    manifest_audit = validate_split_manifest(manifest)
    torch, _, functional, _ = require_torch_stack()
    device, device_audit = select_device(torch, args.device)
    reproducibility = seed_everything(torch, args.seed)

    run_id = safe_run_id(
        args.run_id or datetime.now(timezone.utc).strftime("graphsage-%Y%m%dT%H%M%SZ")
    )
    output_root = path_within_root(root, args.output_root)
    run_dir = output_root / run_id
    report_path = path_within_root(root, args.report)
    if run_dir.exists() and not args.resume and not args.dry_run:
        raise ValueError(f"run directory already exists: {run_dir.relative_to(root)}")

    contract = {
        "split_manifest_sha256": sha256_file(manifest_path),
        "split_content_hash": manifest["split_content_hash"],
        "graph_data_hash": manifest["graph_data_hash"],
        "label_content_hash": manifest["label_content_hash"],
        "decision_content_hash": manifest.get("decision_content_hash"),
        "feature_version": manifest["feature_version"],
        "label_version": manifest["label_version"],
        "snapshot_id": manifest["snapshot_id"],
        "training_scope": manifest.get("training_scope"),
        "seed": args.seed,
        "batch_size": args.batch_size,
        "loss": args.loss,
        "focal_gamma": args.focal_gamma if args.loss == "focal" else None,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "gradient_clip": args.gradient_clip,
        "monitor": args.monitor,
        "threshold": args.threshold,
        "epochs": args.epochs,
        "patience": args.patience,
    }
    config = GraphSAGEConfig(
        model_version=args.model_version,
        feature_ver=manifest["feature_version"],
        label_snapshot=manifest["label_version"],
        input_dim=FEATURE_DIM,
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        num_layers=args.num_layers,
    )
    records, load_audit = load_allowed_splits(root, manifest)
    ready_report = {
        "checked_at": now_iso(),
        "status": "ready" if args.dry_run else "running",
        "run_id": run_id,
        "split_manifest": str(manifest_path.relative_to(root)),
        "run_dir": str(run_dir.relative_to(root)),
        "manifest_audit": manifest_audit,
        "load_audit": load_audit,
        "contract": contract,
        "device": device_audit,
        "reproducibility": reproducibility,
        "held_out_graph_files_loaded": 0,
        "held_out_predictions": 0,
    }
    if args.dry_run:
        write_json(report_path, ready_report)
        print(json.dumps(ready_report, indent=2, sort_keys=True))
        return 0

    train_samples = records["train"]
    validation_samples = records["validation"]
    positive_count = sum(sample["metadata"]["label"] for sample in train_samples)
    negative_count = len(train_samples) - positive_count
    loss_function = build_loss(
        torch, functional, args.loss, positive_count, negative_count, args.focal_gamma
    )
    model = CashFlowGraphSAGE(config).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
        betas=(0.9, 0.95),
        eps=1e-10,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=max(args.epochs, 1), eta_min=args.lr * 0.1
    )

    start_epoch = 1
    best_epoch = 0
    best_metric = -math.inf if args.monitor == "pr_auc" else math.inf
    best_model_state = cpu_state_dict(model)
    history: list[dict[str, Any]] = []
    resumed_from: str | None = None
    carried_best_checkpoint: dict[str, Any] | None = None
    if args.resume:
        resume_path = path_within_root(root, args.resume)
        checkpoint = load_resume_checkpoint(torch, resume_path, device, config, contract)
        source_best_path = resume_path.parent / "best_model.pt"
        if not source_best_path.is_file():
            raise ValueError("resume run is missing its paired best_model.pt")
        carried_best_checkpoint = load_resume_checkpoint(
            torch, source_best_path, device, config, contract
        )
        if carried_best_checkpoint.get("best_epoch") != checkpoint.get("best_epoch"):
            raise ValueError("resume best/last checkpoint disagreement")
        model.load_state_dict(checkpoint["state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        restore_rng_state(torch, checkpoint["rng_state"])
        start_epoch = int(checkpoint["epoch"]) + 1
        if start_epoch > args.epochs:
            raise ValueError("epochs must exceed the epoch stored in the resume checkpoint")
        best_epoch = int(checkpoint["best_epoch"])
        best_metric = float(checkpoint["best_metric"])
        best_model_state = checkpoint["best_model_state_dict"]
        history = list(checkpoint["history"])
        resumed_from = str(resume_path.relative_to(root))

    run_dir.mkdir(parents=True, exist_ok=True)
    best_path = run_dir / "best_model.pt"
    last_path = run_dir / "last_model.pt"
    metrics_path = run_dir / "metrics.json"
    predictions_path = run_dir / "predictions.jsonl"
    run_manifest_path = run_dir / "run_manifest.json"
    curves_json_path = run_dir / "curves.json"
    curves_csv_path = run_dir / "curves.csv"
    if carried_best_checkpoint is not None:
        carried_best_checkpoint = dict(carried_best_checkpoint)
        carried_best_checkpoint["run_id"] = run_id
        carried_best_checkpoint["saved_at"] = now_iso()
        save_checkpoint(torch, best_path, carried_best_checkpoint)

    training_started_at = now_iso()
    started = time.monotonic()
    stale_epochs = max(0, len(history) - best_epoch)
    stopped_early = False
    last_epoch = start_epoch - 1
    for epoch in range(start_epoch, args.epochs + 1):
        last_epoch = epoch
        model.train()
        train_loss_total = 0.0
        gradient_norms: list[float] = []
        learning_rate = float(optimizer.param_groups[0]["lr"])
        for sample_batch in minibatches(train_samples, args.batch_size, args.seed + epoch):
            x, edge_index, batch, target = batch_tensors(torch, sample_batch, device)
            optimizer.zero_grad(set_to_none=True)
            logits = model.forward_logits(x, edge_index, batch)
            loss = loss_function(logits, target)
            if not bool(torch.isfinite(loss).item()):
                raise RuntimeError(f"non-finite loss at epoch {epoch}")
            loss.backward()
            gradient_norm = float(
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.gradient_clip)
                .detach()
                .cpu()
                .item()
            )
            if not math.isfinite(gradient_norm):
                raise RuntimeError(f"non-finite gradient norm at epoch {epoch}")
            optimizer.step()
            train_loss_total += float(loss.detach().cpu().item()) * len(sample_batch)
            gradient_norms.append(gradient_norm)

        validation_metrics, _ = evaluate(
            torch,
            model,
            validation_samples,
            args.batch_size,
            device,
            loss_function,
            args.threshold,
        )
        value = monitor_value(validation_metrics, args.monitor)
        improved = is_improvement(value, best_metric, args.monitor)
        if improved:
            best_metric = value
            best_epoch = epoch
            best_model_state = cpu_state_dict(model)
            stale_epochs = 0
        else:
            stale_epochs += 1
        scheduler.step()
        row = {
            "epoch": epoch,
            "train_loss": train_loss_total / len(train_samples),
            "validation_loss": validation_metrics["loss"],
            "validation_pr_auc": validation_metrics["pr_auc"],
            "validation_roc_auc": validation_metrics["roc_auc"],
            "learning_rate": learning_rate,
            "next_learning_rate": float(optimizer.param_groups[0]["lr"]),
            "gradient_norm_mean": sum(gradient_norms) / len(gradient_norms),
            "gradient_norm_max": max(gradient_norms),
        }
        history.append(row)
        current_state = cpu_state_dict(model)
        payload = checkpoint_payload(
            torch,
            config,
            current_state,
            optimizer,
            scheduler,
            epoch,
            best_epoch,
            best_metric,
            best_model_state,
            history,
            contract,
            run_id,
        )
        save_checkpoint(torch, last_path, payload)
        if improved:
            best_payload = dict(payload)
            best_payload["state_dict"] = best_model_state
            save_checkpoint(torch, best_path, best_payload)
        if stale_epochs >= args.patience:
            stopped_early = True
            break

    if not best_path.exists():
        raise RuntimeError("training completed without creating best_model.pt")

    model.load_state_dict(best_model_state)
    final_metrics: dict[str, dict[str, float]] = {}
    final_scores: dict[str, list[float]] = {}
    for split in TRAINING_SPLITS:
        metrics, scores = evaluate(
            torch,
            model,
            records[split],
            args.batch_size,
            device,
            loss_function,
            args.threshold,
        )
        final_metrics[split] = metrics
        final_scores[split] = scores

    predictions_count = write_predictions(
        predictions_path, records, final_scores, args.threshold
    )
    write_curves(curves_json_path, curves_csv_path, history)
    duration_seconds = time.monotonic() - started
    metrics_payload = {
        "schema_ver": "graphsage-metrics.stage6.v1",
        "run_id": run_id,
        "training_scope": manifest.get("training_scope"),
        "monitor": args.monitor,
        "best_epoch": best_epoch,
        "best_monitor_value": best_metric,
        "last_epoch": last_epoch,
        "epochs_requested": args.epochs,
        "stopped_early": stopped_early,
        "resumed_from": resumed_from,
        "threshold": args.threshold,
        "best_model_metrics": final_metrics,
        "held_out_test": {
            "evaluated": False,
            "graph_files_loaded": 0,
            "predictions": 0,
            "policy": manifest.get("held_out_test_policy"),
        },
    }
    write_json(metrics_path, metrics_payload)

    relative_outputs = {
        "best_model": str(best_path.relative_to(root)),
        "last_model": str(last_path.relative_to(root)),
        "metrics": str(metrics_path.relative_to(root)),
        "predictions": str(predictions_path.relative_to(root)),
        "curves_json": str(curves_json_path.relative_to(root)),
        "curves_csv": str(curves_csv_path.relative_to(root)),
    }
    output_hashes = {
        name: sha256_file(root / path) for name, path in relative_outputs.items()
    }
    run_manifest = {
        "schema_ver": "graphsage-run-manifest.stage6.v1",
        "status": "ok",
        "run_id": run_id,
        "created_at": training_started_at,
        "completed_at": now_iso(),
        "duration_seconds": duration_seconds,
        "git_commit": git_commit(root),
        "command": ["python", "scripts/graphsage_train.py", *sys.argv[1:]],
        "contract": contract,
        "split_manifest": str(manifest_path.relative_to(root)),
        "manifest_audit": manifest_audit,
        "load_audit": load_audit,
        "model_config": asdict(config),
        "optimization": {
            "loss": args.loss,
            "focal_gamma": args.focal_gamma if args.loss == "focal" else None,
            "optimizer": "AdamW",
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "betas": [0.9, 0.95],
            "eps": 1e-10,
            "scheduler": "CosineAnnealingLR",
            "gradient_clip": args.gradient_clip,
            "batch_size": args.batch_size,
            "epochs": args.epochs,
            "patience": args.patience,
            "monitor": args.monitor,
        },
        "seed": args.seed,
        "reproducibility": reproducibility,
        "dependencies": dependency_versions(),
        "device": device_audit,
        "resume": {
            "resumed_from": resumed_from,
            "start_epoch": start_epoch,
        },
        "result": {
            "best_epoch": best_epoch,
            "last_epoch": last_epoch,
            "best_monitor_value": best_metric,
            "stopped_early": stopped_early,
        },
        "held_out_test": {
            "manifest_items": manifest_audit["item_counts"]["held_out_test"],
            "graph_files_loaded": 0,
            "predictions": 0,
            "evaluated": False,
        },
        "outputs": relative_outputs,
        "output_sha256": output_hashes,
        "predictions_written": predictions_count,
    }
    write_json(run_manifest_path, run_manifest)

    report = {
        "checked_at": now_iso(),
        "status": "ok",
        "run_id": run_id,
        "run_manifest": str(run_manifest_path.relative_to(root)),
        "run_manifest_sha256": sha256_file(run_manifest_path),
        "best_epoch": best_epoch,
        "best_validation_pr_auc": final_metrics["validation"]["pr_auc"],
        "last_epoch": last_epoch,
        "resumed_from": resumed_from,
        "training_graph_files_loaded": load_audit["graph_files_loaded_by_split"]["train"],
        "validation_graph_files_loaded": load_audit["graph_files_loaded_by_split"]["validation"],
        "held_out_graph_files_loaded": 0,
        "held_out_predictions": 0,
        "training_scope": manifest.get("training_scope"),
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
