#!/usr/bin/env python3
"""Run provider trace preflight using ETH_PROVIDER_HTTP_URL from .env.local."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from env_local_audit import audit_url, now_iso, parse_env_file, write_json
from trace_endpoint_preflight import main_args as trace_preflight_main_args


def maybe_set_certifi() -> None:
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi  # type: ignore[import-not-found]
    except Exception:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()


def write_probe_plan(
    root: Path,
    out: str,
    env_file: str,
    provider_check: dict[str, Any],
    parse_errors: list[str],
) -> None:
    if parse_errors:
        status = "invalid_env_file"
    elif not provider_check["ok"]:
        status = "missing_or_invalid_provider_http_url"
    else:
        status = "ready_to_probe"
    report = {
        "checked_at": now_iso(),
        "status": status,
        "env_file": env_file,
        "provider_http_check": provider_check,
        "parse_errors": parse_errors,
        "secrets_redacted": True,
        "next_action": "run without --dry-run to test trace capability" if status == "ready_to_probe" else "fix .env.local",
    }
    write_json(root / out, report)
    print(json.dumps(report, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe provider trace capability from .env.local.")
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--queue", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--method", choices=["auto", "debug_traceTransaction", "trace_transaction"], default="auto")
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--out", default="ops/reports/provider-trace-capability-probe.latest.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate .env.local and write a redacted probe plan without making network calls.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    values, parse_errors = parse_env_file(root / args.env_file)
    provider_url = values.get("ETH_PROVIDER_HTTP_URL")
    provider_check = audit_url("ETH_PROVIDER_HTTP_URL", provider_url)
    if args.dry_run or parse_errors or not provider_check["ok"]:
        write_probe_plan(root, args.out, args.env_file, provider_check, parse_errors)
        return 0 if provider_check["ok"] and not parse_errors else 2

    maybe_set_certifi()
    return trace_preflight_main_args(
        [
            "--rpc-url",
            provider_url or "",
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
