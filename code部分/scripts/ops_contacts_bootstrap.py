#!/usr/bin/env python3
"""Create local ops contacts config without overwriting existing values."""

from __future__ import annotations

import argparse
import json
import subprocess
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


def git_ignored(path: str) -> bool:
    result = subprocess.run(["git", "check-ignore", "-q", path], check=False)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap config/ops_contacts.local.json.")
    parser.add_argument("--example", default="config/ops_contacts.example.json")
    parser.add_argument("--out", default="config/ops_contacts.local.json")
    parser.add_argument("--report", default="ops/reports/ops-contacts-bootstrap.latest.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output file.")
    args = parser.parse_args()

    root = Path.cwd()
    example_path = root / args.example
    out_path = root / args.out
    report_path = root / args.report
    created = False
    overwritten = False
    errors: list[str] = []

    existed_before = out_path.exists()
    if not example_path.exists():
        errors.append(f"missing example {args.example}")
    elif existed_before and not args.force:
        pass
    else:
        payload = read_json(example_path)
        write_json(out_path, payload)
        created = not existed_before
        overwritten = existed_before and args.force

    ignored = git_ignored(args.out)
    if not ignored:
        errors.append(f"{args.out} is not git-ignored")

    status = "failed" if errors else ("created" if created else "exists")
    report = {
        "checked_at": now_iso(),
        "status": status,
        "example": args.example,
        "out": args.out,
        "created": created,
        "overwritten": overwritten,
        "git_ignored": ignored,
        "errors": errors,
        "next_action": f"fill all TBD fields in {args.out}" if status in {"created", "exists"} else "fix errors",
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
