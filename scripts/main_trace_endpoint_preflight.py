#!/usr/bin/env python3
"""Run trace endpoint preflight using ETH_MAIN_HTTP_URL from .env.local."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from env_local_audit import audit_url, now_iso, parse_env_file, write_json
from trace_endpoint_preflight import main_args as trace_preflight_main_args


def write_preflight_plan(
    root: Path,
    out: str,
    env_file: str,
    main_check: dict[str, Any],
    parse_errors: list[str],
) -> None:
    if parse_errors:
        status = "invalid_env_file"
    elif not main_check["ok"]:
        status = "missing_or_invalid_main_trace_http_url"
    else:
        status = "ready_to_preflight"
    report = {
        "checked_at": now_iso(),
        "status": status,
        "env_file": env_file,
        "main_trace_http_check": main_check,
        "parse_errors": parse_errors,
        "secrets_redacted": True,
        "next_action": "run without --dry-run to preflight trace endpoint" if status == "ready_to_preflight" else "fix .env.local",
    }
    write_json(root / out, report)
    print(json.dumps(report, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight ETH_MAIN_HTTP_URL from .env.local.")
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--method", choices=["auto", "debug_traceTransaction", "trace_transaction"], default="auto")
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--out", default="ops/reports/trace-endpoint-preflight.latest.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate .env.local without making network calls.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    values, parse_errors = parse_env_file(root / args.env_file)
    main_url = values.get("ETH_MAIN_HTTP_URL")
    main_check = audit_url("ETH_MAIN_HTTP_URL", main_url)
    if args.dry_run or parse_errors or not main_check["ok"]:
        write_preflight_plan(root, args.out, args.env_file, main_check, parse_errors)
        return 0 if main_check["ok"] and not parse_errors else 2

    return trace_preflight_main_args(
        [
            "--rpc-url",
            main_url or "",
            "--queue",
            args.queue,
            "--method",
            args.method,
            "--timeout-s",
            str(args.timeout_s),
            "--out",
            args.out,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
