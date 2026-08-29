#!/usr/bin/env python3
"""Create a secret-free, content-addressed snapshot before paid training work."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PATHS = (
    "data/training",
    "data/replay/trace-bundle.v1",
    "data/replay/graph-inference.v1",
    "ops/reports",
)
DEFAULT_REPORTS = (
    "ops/reports/provider-trace-capability-probe.latest.json",
    "ops/reports/historical-trace-results-audit.latest.json",
    "ops/reports/label-readiness-audit.latest.json",
    "ops/reports/graphsage-train.latest.json",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_path(root: Path, target: Path) -> dict[str, Any]:
    if not target.exists():
        return {
            "path": str(target.relative_to(root)),
            "exists": False,
            "files": 0,
            "bytes": 0,
            "sha256": None,
        }
    files = [target] if target.is_file() else sorted(path for path in target.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    total_bytes = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        file_hash = sha256_file(path)
        size = path.stat().st_size
        total_bytes += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\n")
    return {
        "path": str(target.relative_to(root)),
        "exists": True,
        "files": len(files),
        "bytes": total_bytes,
        "sha256": digest.hexdigest(),
    }


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def dotenv_names(path: Path) -> set[str]:
    names: set[str] = set()
    if not path.exists():
        return names
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" in line:
            name = line.split("=", 1)[0].strip()
            if name:
                names.add(name)
    return names


def environment_policy(env_path: Path) -> dict[str, Any]:
    names = dotenv_names(env_path)
    main_present = "ETH_MAIN_HTTP_URL" in names or bool(os.environ.get("ETH_MAIN_HTTP_URL"))
    provider_present = "ETH_PROVIDER_HTTP_URL" in names or bool(os.environ.get("ETH_PROVIDER_HTTP_URL"))
    return {
        "env_file": str(env_path),
        "env_file_exists": env_path.exists(),
        "eth_main_http_url_present": main_present,
        "eth_provider_http_url_present": provider_present,
        "runtime_mapping": (
            "direct_eth_main_http_url"
            if main_present
            else "ETH_MAIN_HTTP_URL<-ETH_PROVIDER_HTTP_URL"
            if provider_present
            else "unavailable"
        ),
        "ready": main_present or provider_present,
        "secret_values_recorded": False,
    }


def report_states(root: Path) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for relative in DEFAULT_REPORTS:
        path = root / relative
        state: dict[str, Any] = {"path": relative, "exists": path.exists()}
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                state.update(
                    {
                        "status": payload.get("status"),
                        "checked_at": payload.get("checked_at"),
                        "sha256": sha256_file(path),
                    }
                )
            except (OSError, json.JSONDecodeError) as exc:
                state["read_error"] = type(exc).__name__
        states.append(state)
    return states


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot training inputs without copying raw data.")
    parser.add_argument("--path", action="append", dest="paths", default=[])
    parser.add_argument("--env-file", default="../.env.local")
    parser.add_argument("--out", default="ops/snapshots/pre-full-training.v1.json")
    args = parser.parse_args()

    root = Path.cwd()
    selected = args.paths or list(DEFAULT_PATHS)
    snapshots = [snapshot_path(root, root / item) for item in selected]
    environment = environment_policy(root / args.env_file)
    environment["env_file"] = args.env_file
    payload = {
        "schema_ver": "training-run-guard.v1",
        "created_at": now_iso(),
        "git": {
            "commit": git_output(root, "rev-parse", "HEAD"),
            "branch": git_output(root, "branch", "--show-current"),
            "dirty": bool(git_output(root, "status", "--porcelain")),
        },
        "trace_policy": {
            "chain_id": 1,
            "method": "trace_transaction",
            "max_retries": 1,
            "fail_fast": True,
            "raw_trace_committed": False,
        },
        "environment": environment,
        "report_states": report_states(root),
        "snapshots": snapshots,
    }
    write_json(root / args.out, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    ready = all(item["exists"] for item in snapshots) and payload["environment"]["ready"]
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
