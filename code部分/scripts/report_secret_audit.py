#!/usr/bin/env python3
"""Scan generated reports for endpoint secret leakage."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    {
        "name": "alchemy_v2_url_path",
        "pattern": re.compile(r"(?:https?|wss)://[A-Za-z0-9.-]*alchemy\.com/v2/[A-Za-z0-9_-]+"),
    },
    {
        "name": "generic_rpc_v2_url_path",
        "pattern": re.compile(r"(?:https?|wss)://[^\"'\s]+/v2/[A-Za-z0-9_-]+"),
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def scan_file(root: Path, path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    findings = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for item in SECRET_PATTERNS:
            if item["pattern"].search(line):
                findings.append(
                    {
                        "file": str(path.relative_to(root)),
                        "line": line_no,
                        "pattern": item["name"],
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit generated reports for leaked endpoint secrets.")
    parser.add_argument("--input", default="ops/reports")
    parser.add_argument("--out", default="ops/reports/report-secret-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    base = root / args.input
    findings: list[dict[str, Any]] = []
    scanned_files = 0
    if base.exists():
        for path in sorted(base.rglob("*.json")):
            scanned_files += 1
            findings.extend(scan_file(root, path))
    report = {
        "checked_at": now_iso(),
        "status": "ok" if not findings else "failed",
        "input": args.input,
        "scanned_files": scanned_files,
        "findings": findings,
        "patterns": [item["name"] for item in SECRET_PATTERNS],
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
