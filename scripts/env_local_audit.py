#!/usr/bin/env python3
"""Audit .env.local without exposing endpoint secrets."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


EXPORT_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
URL_KEYS = {
    "ETH_PROVIDER_HTTP_URL": {"schemes": {"http", "https"}, "role": "provider_http"},
    "ETH_PROVIDER_WS_URL": {"schemes": {"ws", "wss"}, "role": "provider_ws"},
    "ETH_MAIN_HTTP_URL": {"schemes": {"http", "https"}, "role": "main_trace_http"},
    "ETH_MAIN_WS_URL": {"schemes": {"ws", "wss"}, "role": "main_ws"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    if not path.exists():
        return values, [f"{path} does not exist"]
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = EXPORT_RE.match(line)
        if not match:
            errors.append(f"line {lineno}: unsupported syntax")
            continue
        key, raw_value = match.groups()
        values[key] = unquote(raw_value)
    return values, errors


def audit_url(key: str, value: str | None) -> dict[str, Any]:
    expected = URL_KEYS[key]
    if not value:
        return {
            "name": key,
            "role": expected["role"],
            "present": False,
            "ok": False,
            "scheme": None,
            "host": None,
            "error": "missing",
        }
    parsed = urlparse(value)
    scheme_ok = parsed.scheme in expected["schemes"]
    host_ok = bool(parsed.netloc)
    return {
        "name": key,
        "role": expected["role"],
        "present": True,
        "ok": scheme_ok and host_ok,
        "scheme": parsed.scheme or None,
        "host": parsed.hostname,
        "path_redacted": bool(parsed.path),
        "error": None if scheme_ok and host_ok else "invalid_url_or_scheme",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local environment file without leaking secrets.")
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--out", default="ops/reports/env-local-audit.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    env_path = root / args.env_file
    values, parse_errors = parse_env_file(env_path)
    checks = [audit_url(key, values.get(key)) for key in URL_KEYS]
    by_name = {check["name"]: check for check in checks}
    provider_ready = by_name["ETH_PROVIDER_HTTP_URL"]["ok"] and by_name["ETH_PROVIDER_WS_URL"]["ok"]
    main_trace_ready = by_name["ETH_MAIN_HTTP_URL"]["ok"]
    if parse_errors:
        status = "invalid_env_file"
    elif main_trace_ready:
        status = "main_trace_env_configured"
    elif provider_ready:
        status = "provider_configured_main_missing"
    else:
        status = "missing_provider_or_main"
    report = {
        "checked_at": now_iso(),
        "status": status,
        "env_file": args.env_file,
        "parse_errors": parse_errors,
        "checks": checks,
        "provider_ready": provider_ready,
        "main_trace_ready": main_trace_ready,
        "secrets_redacted": True,
        "next_actions": [
            "run provider trace capability probe against ETH_PROVIDER_HTTP_URL",
            "set ETH_MAIN_HTTP_URL to a trace-capable endpoint if provider probe fails",
        ]
        if not main_trace_ready
        else ["run trace endpoint preflight"],
    }
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
