#!/usr/bin/env python3
"""Run Stage 5 single-graph and one-batch GraphSAGE training gates."""

from __future__ import annotations

import argparse
import json
import math
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphsage_model import CashFlowGraphSAGE, GraphSAGEConfig, graph_tensors, require_torch_stack
from training_runtime import (
    capture_rng_state,
    git_commit,
    parameter_delta_l1,
    restore_rng_state,
    seed_everything,
    select_device,
    sha256_file,
)


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


def load_verified_graph(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    path = root / item["graph_ref"]
    if not path.is_file():
        raise ValueError(f"missing graph {item['graph_ref']}")
    if sha256_file(path) != item.get("graph_sha256"):
        raise ValueError(f"graph hash mismatch {item['tx_hash']}")
    graph = read_json(path)
    if str(graph.get("tx_hash", "")).lower() != item["tx_hash"].lower():
        raise ValueError(f"graph transaction mismatch {item['tx_hash']}")
    if graph.get("feature_ver") != item.get("feature_version"):
        raise ValueError(f"graph feature version mismatch {item['tx_hash']}")
    return graph


def smallest_graph_item(root: Path, items: list[dict[str, Any]], label: int) -> dict[str, Any]:
    candidates = [item for item in items if item.get("label") == label]
    if not candidates:
        raise ValueError(f"training split has no label {label}")
    ranked = [
        ((root / item["graph_ref"]).stat().st_size, item["tx_hash"], item)
        for item in candidates
    ]
    return min(ranked, key=lambda value: (value[0], value[1]))[2]


def optimizer_from_config(torch: Any, model: Any, config: dict[str, Any]) -> Any:
    optimizer = config["optimizer"]
    return torch.optim.AdamW(
        model.parameters(),
        lr=float(optimizer["lr"]),
        weight_decay=float(optimizer["weight_decay"]),
        betas=tuple(float(value) for value in optimizer["betas"]),
        eps=float(optimizer["eps"]),
    )


def model_config(smoke: dict[str, Any], snapshot_id: str) -> GraphSAGEConfig:
    return GraphSAGEConfig(
        label_snapshot=snapshot_id,
        hidden_dim=int(smoke["hidden_dim"]),
        num_layers=int(smoke["num_layers"]),
        dropout=float(smoke["dropout"]),
    )


def clone_parameters(model: Any) -> dict[str, Any]:
    return {name: parameter.detach().cpu().clone() for name, parameter in model.named_parameters()}


def tensors_on_device(graphs: list[dict[str, Any]], device: Any) -> tuple[Any, Any, Any]:
    x, edge_index, batch = graph_tensors(graphs)
    return x.to(device), edge_index.to(device), batch.to(device)


def finite_gradients(torch: Any, model: Any) -> bool:
    gradients = [parameter.grad for parameter in model.parameters() if parameter.grad is not None]
    return bool(gradients) and all(bool(torch.isfinite(gradient).all().item()) for gradient in gradients)


def checkpoint_payload(
    torch: Any,
    model: Any,
    optimizer: Any,
    config: GraphSAGEConfig,
    step: int,
    tx_hashes: list[str],
) -> dict[str, Any]:
    return {
        "schema_ver": "graphsage-training-smoke-checkpoint.stage5.v1",
        "step": step,
        "model_config": asdict(config),
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scheduler_state_dict": None,
        "rng_state": capture_rng_state(torch),
        "training_tx_hashes": tx_hashes,
    }


def restore_and_compare(
    torch: Any,
    checkpoint_path: Path,
    config: GraphSAGEConfig,
    x: Any,
    edge_index: Any,
    batch: Any,
    expected_prediction: Any,
    device: Any,
    original_model: Any,
    original_optimizer: Any,
    target: Any,
    gradient_clip_norm: float,
) -> dict[str, Any]:
    restored = CashFlowGraphSAGE(config).to(device)
    restored_optimizer = torch.optim.AdamW(restored.parameters(), lr=1e-3)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    restored.load_state_dict(checkpoint["model_state_dict"])
    restored_optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    restored.eval()
    with torch.no_grad():
        actual = restored(x, edge_index, batch)
    max_abs_diff = float((expected_prediction - actual).abs().max().detach().cpu().item())
    rng_state = checkpoint.get("rng_state")
    if not isinstance(rng_state, dict):
        raise ValueError("checkpoint RNG state is missing")

    def resume_step(model: Any, optimizer: Any) -> float:
        model.train()
        optimizer.zero_grad(set_to_none=True)
        prediction = model(x, edge_index, batch)
        loss = torch.nn.functional.binary_cross_entropy(prediction, target)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), gradient_clip_norm)
        optimizer.step()
        return float(loss.detach().cpu().item())

    restore_rng_state(torch, rng_state)
    original_loss = resume_step(original_model, original_optimizer)
    restore_rng_state(torch, rng_state)
    restored_loss = resume_step(restored, restored_optimizer)
    resumed_parameter_diff = max(
        float(
            (original_parameter.detach().cpu() - dict(restored.named_parameters())[name].detach().cpu())
            .abs()
            .max()
            .item()
        )
        for name, original_parameter in original_model.named_parameters()
    )
    return {
        "step": checkpoint.get("step"),
        "model_state_restored": True,
        "optimizer_state_restored": bool(restored_optimizer.state_dict().get("state")),
        "scheduler_state_restored": checkpoint.get("scheduler_state_dict") is None,
        "rng_state_restored": True,
        "prediction_max_abs_diff": max_abs_diff,
        "resume_step_loss_abs_diff": abs(original_loss - restored_loss),
        "resume_step_parameter_max_abs_diff": resumed_parameter_diff,
    }


def single_graph_gate(
    root: Path,
    torch: Any,
    smoke: dict[str, Any],
    config: GraphSAGEConfig,
    device: Any,
    item: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    graph = load_verified_graph(root, item)
    x, edge_index, batch = tensors_on_device([graph], device)
    target = torch.tensor([float(item["label"])], dtype=torch.float32, device=device)
    model = CashFlowGraphSAGE(config).to(device)
    optimizer = optimizer_from_config(torch, model, smoke)
    before = clone_parameters(model)
    model.train()
    optimizer.zero_grad(set_to_none=True)
    prediction_before = model(x, edge_index, batch)
    loss_before = torch.nn.functional.binary_cross_entropy(prediction_before, target)
    loss_before.backward()
    gradients_finite = finite_gradients(torch, model)
    gradient_norm = float(
        torch.nn.utils.clip_grad_norm_(model.parameters(), float(smoke["gradient_clip_norm"])).detach().cpu().item()
    )
    optimizer.step()
    parameter_delta = parameter_delta_l1(before, model)
    model.eval()
    with torch.no_grad():
        prediction_after = model(x, edge_index, batch)
        loss_after = torch.nn.functional.binary_cross_entropy(prediction_after, target)

    checkpoint_path = out_dir / "single_graph_checkpoint.pt"
    torch.save(
        checkpoint_payload(torch, model, optimizer, config, 1, [item["tx_hash"]]),
        checkpoint_path,
    )
    restore = restore_and_compare(
        torch,
        checkpoint_path,
        config,
        x,
        edge_index,
        batch,
        prediction_after,
        device,
        model,
        optimizer,
        target,
        float(smoke["gradient_clip_norm"]),
    )
    acceptance = smoke["acceptance"]
    passed = (
        math.isfinite(float(loss_before.item()))
        and math.isfinite(float(loss_after.item()))
        and gradients_finite
        and math.isfinite(gradient_norm)
        and float(loss_after.item()) < float(loss_before.item())
        and parameter_delta >= float(acceptance["minimum_parameter_delta_l1"])
        and restore["prediction_max_abs_diff"] <= float(acceptance["checkpoint_prediction_tolerance"])
        and restore["resume_step_loss_abs_diff"] <= float(acceptance["checkpoint_prediction_tolerance"])
        and restore["resume_step_parameter_max_abs_diff"] <= float(acceptance["checkpoint_prediction_tolerance"])
    )
    return {
        "status": "ok" if passed else "failed",
        "tx_hash": item["tx_hash"],
        "label": item["label"],
        "nodes": len(graph.get("nodes", [])),
        "edges": len(graph.get("edges", [])),
        "input_shape": list(x.shape),
        "edge_index_shape": list(edge_index.shape),
        "prediction_before": float(prediction_before.detach().cpu().item()),
        "prediction_after": float(prediction_after.detach().cpu().item()),
        "loss_before": float(loss_before.detach().cpu().item()),
        "loss_after": float(loss_after.detach().cpu().item()),
        "gradients_finite": gradients_finite,
        "gradient_norm_before_clip": gradient_norm,
        "parameter_delta_l1": parameter_delta,
        "checkpoint": {
            "path": str(checkpoint_path.relative_to(root)),
            "sha256": sha256_file(checkpoint_path),
            **restore,
        },
    }


def one_batch_overfit_gate(
    root: Path,
    torch: Any,
    smoke: dict[str, Any],
    config: GraphSAGEConfig,
    device: Any,
    items: list[dict[str, Any]],
    out_dir: Path,
) -> dict[str, Any]:
    graphs = [load_verified_graph(root, item) for item in items]
    x, edge_index, batch = tensors_on_device(graphs, device)
    target = torch.tensor([float(item["label"]) for item in items], dtype=torch.float32, device=device)
    model = CashFlowGraphSAGE(config).to(device)
    optimizer = optimizer_from_config(torch, model, smoke)
    before = clone_parameters(model)
    model.eval()
    with torch.no_grad():
        initial_prediction = model(x, edge_index, batch)
        initial_loss = torch.nn.functional.binary_cross_entropy(initial_prediction, target)

    loss_curve: list[dict[str, Any]] = []
    gradient_norms: list[float] = []
    gradients_finite = True
    steps = int(smoke["overfit_steps"])
    model.train()
    for step in range(1, steps + 1):
        optimizer.zero_grad(set_to_none=True)
        prediction = model(x, edge_index, batch)
        loss = torch.nn.functional.binary_cross_entropy(prediction, target)
        loss.backward()
        gradients_finite = gradients_finite and finite_gradients(torch, model)
        gradient_norm = float(
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(smoke["gradient_clip_norm"])).detach().cpu().item()
        )
        gradient_norms.append(gradient_norm)
        optimizer.step()
        if step == 1 or step % 10 == 0 or step == steps:
            loss_curve.append({"step": step, "loss": float(loss.detach().cpu().item())})

    model.eval()
    with torch.no_grad():
        final_prediction = model(x, edge_index, batch)
        final_loss = torch.nn.functional.binary_cross_entropy(final_prediction, target)
    parameter_delta = parameter_delta_l1(before, model)
    threshold = float(smoke["acceptance"]["classification_threshold"])
    predicted_labels = (final_prediction >= threshold).to(dtype=torch.long)
    expected_labels = target.to(dtype=torch.long)
    accuracy = float((predicted_labels == expected_labels).float().mean().detach().cpu().item())
    loss_ratio = float(final_loss.item() / max(float(initial_loss.item()), 1e-12))

    checkpoint_path = out_dir / "one_batch_checkpoint.pt"
    torch.save(
        checkpoint_payload(torch, model, optimizer, config, steps, [item["tx_hash"] for item in items]),
        checkpoint_path,
    )
    restore = restore_and_compare(
        torch,
        checkpoint_path,
        config,
        x,
        edge_index,
        batch,
        final_prediction,
        device,
        model,
        optimizer,
        target,
        float(smoke["gradient_clip_norm"]),
    )
    acceptance = smoke["acceptance"]
    passed = (
        gradients_finite
        and all(math.isfinite(value) for value in gradient_norms)
        and float(final_loss.item()) <= float(acceptance["maximum_final_loss"])
        and loss_ratio <= float(acceptance["maximum_final_to_initial_loss_ratio"])
        and parameter_delta >= float(acceptance["minimum_parameter_delta_l1"])
        and accuracy == 1.0
        and restore["prediction_max_abs_diff"] <= float(acceptance["checkpoint_prediction_tolerance"])
        and restore["resume_step_loss_abs_diff"] <= float(acceptance["checkpoint_prediction_tolerance"])
        and restore["resume_step_parameter_max_abs_diff"] <= float(acceptance["checkpoint_prediction_tolerance"])
    )
    return {
        "status": "ok" if passed else "failed",
        "tx_hashes": [item["tx_hash"] for item in items],
        "labels": [item["label"] for item in items],
        "graphs": len(items),
        "nodes": int(x.shape[0]),
        "edges": int(edge_index.shape[1]),
        "initial_loss": float(initial_loss.detach().cpu().item()),
        "final_loss": float(final_loss.detach().cpu().item()),
        "final_to_initial_loss_ratio": loss_ratio,
        "initial_predictions": [float(value) for value in initial_prediction.detach().cpu().tolist()],
        "final_predictions": [float(value) for value in final_prediction.detach().cpu().tolist()],
        "accuracy": accuracy,
        "gradients_finite": gradients_finite,
        "gradient_norm": {
            "minimum": min(gradient_norms),
            "maximum": max(gradient_norms),
            "final": gradient_norms[-1],
        },
        "parameter_delta_l1": parameter_delta,
        "loss_curve": loss_curve,
        "checkpoint": {
            "path": str(checkpoint_path.relative_to(root)),
            "sha256": sha256_file(checkpoint_path),
            **restore,
        },
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path.cwd()
    smoke = read_json(root / args.config)
    manifest = read_json(root / args.split_manifest)
    audit = read_json(root / args.split_audit)
    if audit.get("status") != "ok" or audit.get("errors"):
        raise ValueError("Stage 4 split audit is not clean")
    if manifest.get("frozen") is not True:
        raise ValueError("split manifest is not frozen")
    if smoke["data_policy"]["allowed_split"] != "train":
        raise ValueError("Stage 5 smoke policy must restrict graph loading to train")

    torch, _, _, _ = require_torch_stack()
    torch.set_num_threads(1)
    seed_report = seed_everything(torch, int(smoke["seed"]))
    requested_device = args.device or smoke["device"]
    device, device_report = select_device(torch, requested_device)
    train_items = [item for item in manifest.get("items", []) if item.get("split") == "train"]
    split_counts_seen = {
        split: sum(item.get("split") == split for item in manifest.get("items", []))
        for split in ("train", "validation", "held_out_test")
    }
    positive = smallest_graph_item(root, train_items, 1)
    negative = smallest_graph_item(root, train_items, 0)
    selected = [positive, negative]

    config = model_config(smoke, manifest["snapshot_id"])
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    single_graph = single_graph_gate(root, torch, smoke, config, device, positive, out_dir)
    seed_everything(torch, int(smoke["seed"]))
    one_batch = one_batch_overfit_gate(root, torch, smoke, config, device, selected, out_dir)
    errors = []
    if single_graph["status"] != "ok":
        errors.append("single_graph_gate_failed")
    if one_batch["status"] != "ok":
        errors.append("one_batch_overfit_gate_failed")

    return {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "stage": 5,
        "scope": "minimum_training_closure",
        "git_commit": git_commit(root),
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
        },
        "seed": seed_report,
        "device": device_report,
        "model_config": asdict(config),
        "optimizer_config": smoke["optimizer"],
        "gradient_clip_norm": smoke["gradient_clip_norm"],
        "data_contract": {
            "split_manifest": args.split_manifest,
            "split_manifest_sha256": sha256_file(root / args.split_manifest),
            "split_content_hash": manifest.get("split_content_hash"),
            "graph_data_hash": manifest.get("graph_data_hash"),
            "feature_version": manifest.get("feature_version"),
            "label_version": manifest.get("label_version"),
            "split_counts_seen_in_manifest": split_counts_seen,
            "graph_files_loaded": 2,
            "train_graphs_loaded": 2,
            "validation_graphs_loaded": 0,
            "held_out_test_graphs_loaded": 0,
            "held_out_test_predictions": 0,
        },
        "single_graph": single_graph,
        "one_batch_overfit": one_batch,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage 5 GraphSAGE training smoke gates.")
    parser.add_argument("--config", default="config/training_smoke.stage5.v1.json")
    parser.add_argument("--split-manifest", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--split-audit", default="ops/reports/split-manifest-audit.latest.json")
    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"))
    parser.add_argument("--out-dir", default="models/graphsage/runs/stage5-smoke")
    parser.add_argument("--report", default="ops/reports/training-smoke.stage5.latest.json")
    args = parser.parse_args()
    root = Path.cwd()
    try:
        report = run(args)
    except Exception as exc:  # noqa: BLE001 - persist a concise failure report.
        report = {
            "checked_at": now_iso(),
            "status": "failed",
            "stage": 5,
            "scope": "minimum_training_closure",
            "git_commit": git_commit(root),
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
