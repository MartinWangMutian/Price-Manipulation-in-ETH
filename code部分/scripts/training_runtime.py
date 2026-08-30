#!/usr/bin/env python3
"""Shared deterministic runtime helpers for GraphSAGE training checks."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import random
import subprocess
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_device(torch: Any, requested: str = "auto") -> tuple[Any, dict[str, Any]]:
    requested = requested.lower()
    availability = {
        "cuda": bool(torch.cuda.is_available()),
        "mps_built": bool(torch.backends.mps.is_built()),
        "mps": bool(torch.backends.mps.is_available()),
        "cpu": True,
    }
    if requested == "auto":
        selected = "cuda" if availability["cuda"] else "mps" if availability["mps"] else "cpu"
    elif requested == "cuda":
        if not availability["cuda"]:
            raise RuntimeError("CUDA was requested but is unavailable")
        selected = "cuda"
    elif requested == "mps":
        if not availability["mps"]:
            raise RuntimeError("MPS was requested but is unavailable")
        selected = "mps"
    elif requested == "cpu":
        selected = "cpu"
    else:
        raise ValueError(f"unsupported device {requested!r}")
    return torch.device(selected), {
        "requested": requested,
        "selected": selected,
        "availability": availability,
    }


def seed_everything(torch: Any, seed: int) -> dict[str, Any]:
    random.seed(seed)
    try:
        import numpy

        numpy.random.seed(seed % (2**32))
    except Exception:  # noqa: BLE001 - numpy is optional to the helper.
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    return {
        "seed": seed,
        "deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
    }


def capture_rng_state(torch: Any) -> dict[str, Any]:
    state: dict[str, Any] = {"cpu": torch.get_rng_state()}
    if torch.cuda.is_available():
        state["cuda"] = torch.cuda.get_rng_state_all()
    if torch.backends.mps.is_available() and hasattr(torch.mps, "get_rng_state"):
        state["mps"] = torch.mps.get_rng_state()
    return state


def restore_rng_state(torch: Any, state: dict[str, Any]) -> None:
    torch.set_rng_state(state["cpu"].cpu())
    if "cuda" in state and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state["cuda"])
    if "mps" in state and torch.backends.mps.is_available() and hasattr(torch.mps, "set_rng_state"):
        torch.mps.set_rng_state(state["mps"].cpu())


def normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def locked_requirements(path: Path) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"unlocked requirement line: {line}")
        name, version = line.split("==", 1)
        requirements[normalize_package_name(name)] = version
    return requirements


def installed_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def audit_locked_requirements(path: Path) -> tuple[dict[str, Any], list[str]]:
    expected = locked_requirements(path)
    observed: dict[str, str | None] = {}
    errors: list[str] = []
    for name, version in sorted(expected.items()):
        installed = installed_version(name)
        observed[name] = installed
        if installed != version:
            errors.append(f"dependency mismatch {name}: expected={version} observed={installed}")
    return {
        "lock_path": str(path),
        "lock_sha256": sha256_file(path),
        "locked_packages": len(expected),
        "expected": expected,
        "observed": observed,
    }, errors


def git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def parameter_delta_l1(before: dict[str, Any], model: Any) -> float:
    total = 0.0
    for name, parameter in model.named_parameters():
        total += float((parameter.detach().cpu() - before[name]).abs().sum().item())
    return total
