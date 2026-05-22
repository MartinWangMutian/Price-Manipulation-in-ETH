#!/usr/bin/env python3
"""Train the GraphSAGE cash-flow graph classifier when labeled rich graphs exist."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphsage_model import (
    CashFlowGraphSAGE,
    GraphSAGEConfig,
    dependency_status,
    graph_tensors,
    load_graph_records,
    require_torch_stack,
    write_manifest,
)


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


def load_label_map(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    payload = read_json(path)
    labels: dict[str, int] = {}
    candidates = payload.get("labels", payload.get("items", []))
    if isinstance(candidates, list):
        for item in candidates:
            if not isinstance(item, dict):
                continue
            tx_hash = item.get("tx_hash")
            label = item.get("label")
            if isinstance(tx_hash, str) and label in {0, 1}:
                labels[tx_hash.lower()] = int(label)
    return labels


def class_balanced_focal_loss(pred: Any, target: Any, gamma: float = 2.0) -> Any:
    torch, _, functional, _ = require_torch_stack()
    pred = pred.clamp(1e-6, 1.0 - 1e-6)
    positives = target.sum().clamp_min(1.0)
    negatives = (target.numel() - target.sum()).clamp_min(1.0)
    alpha = negatives / (positives + negatives)
    bce = functional.binary_cross_entropy(pred, target, reduction="none")
    pt = torch.where(target == 1, pred, 1.0 - pred)
    weights = torch.where(target == 1, alpha, 1.0 - alpha)
    return (weights * ((1.0 - pt) ** gamma) * bce).mean()


def main() -> int:
    parser = argparse.ArgumentParser(description="Train GraphSAGE on labeled graph replay files.")
    parser.add_argument("--graphs", default="data/replay/graph-inference.v1")
    parser.add_argument("--labels", default="data/training/graph_labels.v1.json")
    parser.add_argument("--out-dir", default="models/graphsage/latest")
    parser.add_argument("--report", default="ops/reports/graphsage-train.latest.json")
    parser.add_argument("--model-version", default="graphsage.v1")
    parser.add_argument("--label-snapshot", default="label-snapshot.v1")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    config = GraphSAGEConfig(
        model_version=args.model_version,
        label_snapshot=args.label_snapshot,
    )
    graphs = load_graph_records(root / args.graphs)
    label_map = load_label_map(root / args.labels)
    labeled_graphs = [
        graph for graph in graphs if str(graph.get("tx_hash", "")).lower() in label_map
    ]
    labels = [
        label_map[str(graph.get("tx_hash", "")).lower()]
        for graph in labeled_graphs
    ]

    report: dict[str, Any] = {
        "checked_at": now_iso(),
        "status": "blocked",
        "model_version": config.model_version,
        "feature_ver": config.feature_ver,
        "graphs_seen": len(graphs),
        "labeled_graphs": len(labeled_graphs),
        "dependencies": dependency_status(),
        "checkpoint_path": None,
        "manifest_path": None,
        "blocking_reasons": [],
    }
    if not all(report["dependencies"].values()):
        report["blocking_reasons"].append("torch_or_torch_geometric_missing")
    if not labeled_graphs:
        report["blocking_reasons"].append("no_labeled_graph_replay_records")
    if len(set(labels)) < 2:
        report["blocking_reasons"].append("labels_must_include_positive_and_negative_classes")
    if args.dry_run or report["blocking_reasons"]:
        write_json(root / args.report, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    torch, _, _, _ = require_torch_stack()
    model = CashFlowGraphSAGE(config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    target = torch.tensor(labels, dtype=torch.float32)
    x, edge_index, batch = graph_tensors(labeled_graphs)
    losses: list[float] = []
    model.train()
    for _ in range(args.epochs):
        optimizer.zero_grad()
        pred = model(x, edge_index, batch)
        loss = class_balanced_focal_loss(pred, target)
        loss.backward()
        optimizer.step()
        losses.append(round(float(loss.detach().cpu().item()), 6))

    out_dir = root / args.out_dir
    checkpoint_path = out_dir / "model.pt"
    manifest_path = out_dir / "manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save({"config": asdict(config), "state_dict": model.state_dict()}, checkpoint_path)
    write_manifest(
        manifest_path,
        config,
        {
            "trained_at": now_iso(),
            "training_graphs": len(labeled_graphs),
            "epochs": args.epochs,
            "final_loss": losses[-1],
        },
    )
    report.update(
        {
            "status": "ok",
            "checkpoint_path": str(checkpoint_path.relative_to(root)),
            "manifest_path": str(manifest_path.relative_to(root)),
            "blocking_reasons": [],
            "loss_history": losses,
        }
    )
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
