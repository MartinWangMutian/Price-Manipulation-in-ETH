#!/usr/bin/env python3
"""Audit the isolated PyTorch/PyG environment and device contract."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training_runtime import audit_locked_requirements, git_commit, select_device


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Stage 5 GraphSAGE training environment.")
    parser.add_argument("--lock", default="requirements/graphsage-stage5.lock.txt")
    parser.add_argument("--device", default="auto", choices=("auto", "cuda", "mps", "cpu"))
    parser.add_argument("--out", default="ops/reports/training-environment.stage5.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    errors: list[str] = []
    dependency_audit, dependency_errors = audit_locked_requirements(Path(args.lock))
    errors.extend(dependency_errors)
    try:
        import torch
        import torch_geometric
        from torch_geometric.nn import SAGEConv

        device, device_report = select_device(torch, args.device)
        torch.manual_seed(20260830)
        x = torch.randn(4, 8, dtype=torch.float32)
        edge_index = torch.tensor([[0, 1, 2, 3], [1, 2, 3, 0]], dtype=torch.long)
        cpu_layer = SAGEConv(8, 4)
        expected_state = {key: value.detach().clone() for key, value in cpu_layer.state_dict().items()}
        cpu_output = cpu_layer(x, edge_index)
        selected_layer = SAGEConv(8, 4)
        selected_layer.load_state_dict(expected_state)
        selected_layer = selected_layer.to(device)
        selected_output = selected_layer(x.to(device), edge_index.to(device))
        output_contract = {
            "input_shape": list(x.shape),
            "edge_index_shape": list(edge_index.shape),
            "cpu_output_shape": list(cpu_output.shape),
            "selected_output_shape": list(selected_output.shape),
            "cpu_output_dtype": str(cpu_output.dtype),
            "selected_output_dtype": str(selected_output.dtype),
            "selected_output_finite": bool(torch.isfinite(selected_output).all().item()),
            "format_consistent": (
                tuple(cpu_output.shape) == tuple(selected_output.shape)
                and cpu_output.dtype == selected_output.dtype
            ),
        }
        if not output_contract["selected_output_finite"]:
            errors.append("selected-device SAGEConv output is non-finite")
        if not output_contract["format_consistent"]:
            errors.append("selected device changed the SAGEConv output contract")
        versions = {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_geometric": torch_geometric.__version__,
        }
    except Exception as exc:  # noqa: BLE001 - persist environment failure evidence.
        errors.append(f"runtime import/operator failure: {type(exc).__name__}: {exc}")
        device_report = {"requested": args.device, "selected": None, "availability": {}}
        output_contract = {}
        versions = {"python": platform.python_version(), "torch": None, "torch_geometric": None}

    environment_prefix = Path(sys.prefix)
    try:
        prefix_ref = str(environment_prefix.relative_to(root))
    except ValueError:
        prefix_ref = environment_prefix.name
    executable_ref = f"{prefix_ref}/bin/python"
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not errors else "failed",
        "git_commit": git_commit(root),
        "environment_prefix": prefix_ref,
        "python_executable": executable_ref,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "versions": versions,
        "dependencies": dependency_audit,
        "device": device_report,
        "output_contract": output_contract,
        "errors": errors,
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
