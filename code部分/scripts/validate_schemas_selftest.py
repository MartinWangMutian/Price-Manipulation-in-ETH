#!/usr/bin/env python3
"""Self-test for the repository's dependency-free schema validator."""

from validate_schemas import validate_instance


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_ver", "score", "created_at"],
    "properties": {
        "schema_ver": {"const": "sample.v1"},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "created_at": {"type": "string", "format": "date-time"},
    },
}


def main() -> int:
    valid = {
        "schema_ver": "sample.v1",
        "score": 0.4,
        "created_at": "2026-05-14T00:00:00Z",
    }
    assert validate_instance(valid, SCHEMA, "valid") == []

    invalid = dict(valid, score=1.4, unexpected=True)
    errors = validate_instance(invalid, SCHEMA, "invalid")
    assert any("above maximum" in error for error in errors)
    assert any("unexpected property" in error for error in errors)
    print("validate_schemas_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
