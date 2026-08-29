#!/usr/bin/env python3
"""Synthetic checks for historical_trace_replay.py."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import historical_trace_replay as replay


TX_HASH = "0x" + "12" * 32


def queue_item() -> dict[str, object]:
    return {
        "queue_id": "queue-1",
        "incident_id": "synthetic_incident",
        "chain": "ethereum",
        "chain_id": 1,
        "tx_hash": TX_HASH,
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        item = queue_item()

        assert replay.validate_queue_item(item) == []
        assert replay.validate_queue_item({**item, "chain_id": 5}) == [
            "only ethereum chain_id=1 items are supported"
        ]

        geth_result = {
            "type": "CALL",
            "from": "0x" + "11" * 20,
            "to": "0x" + "22" * 20,
            "input": "0xabcdef01",
            "gas": "0x5208",
            "gasUsed": "0x5208",
            "calls": [
                {
                    "type": "STATICCALL",
                    "from": "0x" + "22" * 20,
                    "to": "0x" + "33" * 20,
                    "input": "0x",
                    "gas": "0x100",
                    "gasUsed": "0x80",
                }
            ],
        }
        calls, logs, state_diff = replay.normalize_trace("debug_traceTransaction", geth_result)
        assert len(calls) == 2, calls
        assert calls[1]["depth"] == 1, calls
        assert logs == [], logs
        assert state_diff == {}, state_diff

        erigon_result = [
            {
                "action": {
                    "callType": "call",
                    "from": "0x" + "11" * 20,
                    "to": "0x" + "22" * 20,
                    "input": "0xabcdef01",
                },
                "result": {"gasUsed": "0x5208", "output": "0x"},
                "traceAddress": [],
                "type": "call",
            }
        ]
        calls, logs, state_diff = replay.normalize_trace("trace_transaction", erigon_result)
        assert len(calls) == 1, calls
        assert logs == [], logs
        assert state_diff == {}, state_diff

        original_rpc_call = replay.rpc_call
        try:
            replay.rpc_call = lambda url, method, params, timeout_s: (  # type: ignore[assignment]
                {"result": geth_result},
                1.23,
            )
            bundle, meta = replay.trace_item(
                root,
                item,
                "http://example.invalid",
                "debug_traceTransaction",
                1.0,
                0,
            )
            assert bundle["trace_status"] == "ok", bundle
            assert bundle["trace_source"] == "debug_traceTransaction", bundle
            assert bundle["raw_trace_ref"], bundle
            assert meta["selected"] == "debug_traceTransaction", meta
            assert (root / str(bundle["raw_trace_ref"])).exists(), bundle

            replay.rpc_call = lambda url, method, params, timeout_s: (  # type: ignore[assignment]
                {"error": {"code": -32000, "message": "missing trie node"}},
                2.34,
            )
            bundle, meta = replay.trace_item(
                root,
                item,
                "http://example.invalid",
                "debug_traceTransaction",
                1.0,
                1,
            )
            assert bundle["trace_status"] == "failed", bundle
            assert bundle["trace_error"]["code"] == "historical_trace_failed", bundle
            assert len(meta["attempts"]) == 2, meta

            calls = {"count": 0}

            def rpc_erigon_only(url, method, params, timeout_s):
                calls["count"] += 1
                if method == "debug_traceTransaction":
                    return {"error": {"code": -32601, "message": "method not found"}}, 1.0
                return {"result": [{"type": "call", "traceAddress": []}]}, 1.0

            replay.rpc_call = rpc_erigon_only  # type: ignore[assignment]
            bundle, meta = replay.trace_item_auto(
                root,
                item,
                "http://example.invalid",
                "auto",
                1.0,
                0,
            )
            assert bundle["trace_status"] == "ok", bundle
            assert bundle["trace_source"] == "trace_transaction", bundle
            assert meta["selected"] == "trace_transaction", meta
            assert calls["count"] == 2, calls
        finally:
            replay.rpc_call = original_rpc_call  # type: ignore[assignment]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        queue_path = root / "queue.json"
        report_path = root / "report.json"
        replay.write_json(
            queue_path,
            {
                "schema_ver": "trace-replay-queue.v1",
                "items": [queue_item()],
            },
        )
        with patch.object(
            replay,
            "rpc_call",
            return_value=({"error": {"code": -32000, "message": "missing trie node"}}, 2.34),
        ), patch.object(replay.Path, "cwd", return_value=root):
            exit_code = replay.main_args(
                [
                    "--queue",
                    str(queue_path.relative_to(root)),
                    "--rpc-url",
                    "http://example.invalid",
                    "--retries",
                    "0",
                    "--out",
                    str(report_path.relative_to(root)),
                ]
            )
        assert exit_code == 2, exit_code
        report = replay.read_json(report_path)
        assert report["status"] == "degraded", report
        assert report["fail_fast"] is True, report
        assert report["max_retries"] == 0, report
        assert report["written_trace_bundles"] == 0, report
        assert report["failed_trace_bundles"] == 1, report
        assert not list((root / "data" / "replay" / "trace-bundle.v1").glob("**/*.json"))

    try:
        replay.retry_count("2")
        raise AssertionError("retry_count accepted a value greater than one")
    except replay.argparse.ArgumentTypeError:
        pass

    print("historical_trace_replay_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
