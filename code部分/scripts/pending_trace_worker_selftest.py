#!/usr/bin/env python3
"""Synthetic normalization checks for pending_trace_worker.py."""

from __future__ import annotations

from pending_trace_worker import normalize_trace


def main() -> int:
    root_log = {"address": "0x" + "11" * 20, "topics": [], "data": "0x"}
    child_log = {"address": "0x" + "22" * 20, "topics": [], "data": "0x"}
    calls, logs, state_diff = normalize_trace(
        "debug_traceCall",
        {
            "type": "CALL",
            "from": "0x" + "33" * 20,
            "to": "0x" + "44" * 20,
            "logs": [root_log],
            "calls": [
                {
                    "type": "CALL",
                    "from": "0x" + "44" * 20,
                    "to": "0x" + "55" * 20,
                    "logs": [child_log],
                }
            ],
        },
    )
    assert len(calls) == 2, calls
    assert logs == [root_log, child_log], logs
    assert state_diff == {}, state_diff
    print("pending_trace_worker_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
