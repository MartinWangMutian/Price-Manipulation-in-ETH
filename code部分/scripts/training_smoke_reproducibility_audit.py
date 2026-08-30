#!/usr/bin/env python3
"""Compare two Stage 5 smoke runs while ignoring timestamps and output paths."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def stable_projection(report: dict[str, Any]) -> dict[str, Any]:
    single = report["single_graph"]
    batch = report["one_batch_overfit"]
    return {
        "status": report["status"],
        "device": report["device"]["selected"],
        "seed": report["seed"],
        "model_config": report["model_config"],
        "optimizer_config": report["optimizer_config"],
        "data_hashes": {
            "split": report["data_contract"]["split_content_hash"],
            "graphs": report["data_contract"]["graph_data_hash"],
        },
        "single_graph": {
            "tx_hash": single["tx_hash"],
            "label": single["label"],
            "loss_before": single["loss_before"],
            "loss_after": single["loss_after"],
            "prediction_before": single["prediction_before"],
            "prediction_after": single["prediction_after"],
            "gradient_norm": single["gradient_norm_before_clip"],
            "parameter_delta_l1": single["parameter_delta_l1"],
            "checkpoint_sha256": single["checkpoint"]["sha256"],
            "checkpoint_restore": {
                key: value for key, value in single["checkpoint"].items() if key not in {"path", "sha256"}
            },
        },
        "one_batch_overfit": {
            "tx_hashes": batch["tx_hashes"],
            "labels": batch["labels"],
            "initial_loss": batch["initial_loss"],
            "final_loss": batch["final_loss"],
            "initial_predictions": batch["initial_predictions"],
            "final_predictions": batch["final_predictions"],
            "accuracy": batch["accuracy"],
            "gradient_norm": batch["gradient_norm"],
            "parameter_delta_l1": batch["parameter_delta_l1"],
            "loss_curve": batch["loss_curve"],
            "checkpoint_sha256": batch["checkpoint"]["sha256"],
            "checkpoint_restore": {
                key: value for key, value in batch["checkpoint"].items() if key not in {"path", "sha256"}
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit deterministic Stage 5 smoke reproduction.")
    parser.add_argument("--first", default="ops/reports/training-smoke.stage5.latest.json")
    parser.add_argument("--second", required=True)
    parser.add_argument("--out", default="ops/reports/training-smoke-reproducibility.stage5.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    first = stable_projection(read_json(root / args.first))
    second_path = Path(args.second)
    second = stable_projection(read_json(second_path if second_path.is_absolute() else root / second_path))
    identical = first == second
    report = {
        "checked_at": now_iso(),
        "status": "ok" if identical else "failed",
        "first_run": Path(args.first).name,
        "second_run": second_path.name,
        "stable_fields_identical": identical,
        "device": first["device"],
        "seed": first["seed"]["seed"],
        "single_graph_checkpoint_sha256": first["single_graph"]["checkpoint_sha256"],
        "one_batch_checkpoint_sha256": first["one_batch_overfit"]["checkpoint_sha256"],
        "errors": [] if identical else ["stable smoke-run fields differ"],
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if identical else 1


if __name__ == "__main__":
    raise SystemExit(main())
