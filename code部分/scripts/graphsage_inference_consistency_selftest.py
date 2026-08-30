#!/usr/bin/env python3
"""Fast numeric checks for GraphSAGE inference consistency auditing."""

from __future__ import annotations

from graphsage_inference_consistency_audit import max_absolute_difference


def main() -> int:
    assert max_absolute_difference([], []) == 0.0
    assert max_absolute_difference([0.1, 0.3], [0.1, 0.3000001]) < 1e-6
    try:
        max_absolute_difference([0.1], [0.1, 0.2])
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched prediction lengths were accepted")
    print("graphsage_inference_consistency_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
