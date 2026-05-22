#!/usr/bin/env python3
"""Lightweight Phase 1 schema consistency checks."""

from __future__ import annotations

import json
from pathlib import Path


COMMON_FIELDS = {
    "event_id",
    "schema_ver",
    "chain_id",
    "created_at",
    "idempotency_key",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    topics = load_json(root / "config/message_topics.json")["topics"]
    errors: list[str] = []

    for topic in topics:
        schema_path = root / topic["schema"]
        if not schema_path.exists():
            errors.append(f"missing schema for {topic['name']}: {schema_path}")
            continue
        schema = load_json(schema_path)
        required = set(schema.get("required", []))
        missing = sorted(COMMON_FIELDS - required)
        if missing:
            errors.append(f"{topic['name']} missing required fields: {missing}")
        schema_ver = schema.get("properties", {}).get("schema_ver", {}).get("const")
        if schema_ver != topic["name"]:
            errors.append(
                f"{topic['name']} schema_ver const mismatch: {schema_ver!r}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"validated {len(topics)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
