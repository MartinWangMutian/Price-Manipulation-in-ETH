#!/usr/bin/env python3
"""Validate topic metadata and committed replay records without dependencies."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


COMMON_FIELDS = {
    "event_id",
    "schema_ver",
    "chain_id",
    "created_at",
    "idempotency_key",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def validate_instance(value: Any, schema: dict[str, Any], location: str) -> list[str]:
    """Validate the JSON Schema subset used by this repository."""
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(type_matches(value, item) for item in types):
            return [f"{location}: expected {' or '.join(types)}, got {type(value).__name__}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: expected constant {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: value {value!r} is not in {schema['enum']!r}")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{location}: string is shorter than minLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"{location}: value does not match {pattern!r}")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{location}: invalid date-time {value!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{location}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{location}: value is above maximum {schema['maximum']}")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{location}: array has fewer than minItems entries")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_instance(item, item_schema, f"{location}[{index}]"))

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{location}: missing required property {key!r}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                errors.extend(validate_instance(item, properties[key], f"{location}.{key}"))
            elif additional is False:
                errors.append(f"{location}: unexpected property {key!r}")
            elif isinstance(additional, dict):
                errors.extend(validate_instance(item, additional, f"{location}.{key}"))

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    topics = load_json(root / "config/message_topics.json")["topics"]
    errors: list[str] = []
    schemas: dict[str, dict[str, Any]] = {}
    record_count = 0

    for topic in topics:
        topic_name = topic["name"]
        schema_path = root / topic["schema"]
        if not schema_path.exists():
            errors.append(f"missing schema for {topic_name}: {schema_path}")
            continue
        schema = load_json(schema_path)
        schemas[topic_name] = schema
        required = set(schema.get("required", []))
        missing = sorted(COMMON_FIELDS - required)
        if missing:
            errors.append(f"{topic_name} missing required fields: {missing}")
        schema_ver = schema.get("properties", {}).get("schema_ver", {}).get("const")
        if schema_ver != topic_name:
            errors.append(f"{topic_name} schema_ver const mismatch: {schema_ver!r}")

    for topic_name, schema in schemas.items():
        replay_dir = root / "data/replay" / topic_name
        for path in sorted(replay_dir.rglob("*.json")):
            record_count += 1
            try:
                record = load_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{path.relative_to(root)}: cannot parse JSON: {exc}")
                continue
            errors.extend(validate_instance(record, schema, str(path.relative_to(root))))

    rag_schema = load_json(root / "schemas/rag-document.v1.schema.json")
    rag_documents = load_json(root / "data/rag/documents.seed.json").get("documents", [])
    for index, document in enumerate(rag_documents):
        record_count += 1
        errors.extend(
            validate_instance(document, rag_schema, f"data/rag/documents.seed.json.documents[{index}]")
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"validated {len(schemas) + 1} schemas and {record_count} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
