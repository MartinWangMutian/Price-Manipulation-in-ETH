#!/usr/bin/env python3
"""Synthetic checks for trace_endpoint_preflight.py."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import trace_endpoint_preflight as preflight
from historical_trace_replay import write_json


def queue_payload() -> dict[str, object]:
    return {
        "schema_ver": "trace-replay-queue.v1",
        "items": [
            {
                "queue_id": "queue-1",
                "incident_id": "synthetic_incident",
                "chain": "ethereum",
                "chain_id": 1,
                "tx_hash": "0x" + "12" * 32,
            }
        ],
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_json(root / "queue.json", queue_payload())

        def rpc_ok(url: str, method: str, params: list[object], timeout_s: float):
            if method == "eth_chainId":
                return {"result": "0x1"}, 1.0
            return {"result": {"type": "CALL", "calls": []}}, 2.0

        with patch.object(preflight.Path, "cwd", return_value=root), patch.object(preflight, "rpc_call", side_effect=rpc_ok):
            exit_code = preflight.main_args(
                [
                    "--queue",
                    "queue.json",
                    "--rpc-url",
                    "http://example.invalid",
                    "--out",
                    "preflight-ok.json",
                ]
            )
        assert exit_code == 0, exit_code
        report = preflight.read_json(root / "preflight-ok.json")
        assert report["status"] == "ok", report
        assert len(report["checks"]) == 2, report
        assert report["selected_method"] == "debug_traceTransaction", report

        def rpc_bad_trace(url: str, method: str, params: list[object], timeout_s: float):
            if method == "eth_chainId":
                return {"result": "0x1"}, 1.0
            return {"error": {"code": -32601, "message": "method not found"}}, 2.0

        with patch.object(preflight.Path, "cwd", return_value=root), patch.object(preflight, "rpc_call", side_effect=rpc_bad_trace):
            exit_code = preflight.main_args(
                [
                    "--queue",
                    "queue.json",
                    "--rpc-url",
                    "http://example.invalid",
                    "--out",
                    "preflight-bad.json",
                ]
            )
        assert exit_code == 2, exit_code
        report = preflight.read_json(root / "preflight-bad.json")
        assert report["status"] == "degraded", report
        assert report["checks"][1]["ok"] is False, report

        def rpc_erigon_only(url: str, method: str, params: list[object], timeout_s: float):
            if method == "eth_chainId":
                return {"result": "0x1"}, 1.0
            if method == "debug_traceTransaction":
                return {"error": {"code": -32601, "message": "method not found"}}, 2.0
            return {"result": [{"type": "call", "traceAddress": []}]}, 3.0

        with patch.object(preflight.Path, "cwd", return_value=root), patch.object(preflight, "rpc_call", side_effect=rpc_erigon_only):
            exit_code = preflight.main_args(
                [
                    "--queue",
                    "queue.json",
                    "--method",
                    "auto",
                    "--rpc-url",
                    "http://example.invalid",
                    "--out",
                    "preflight-erigon.json",
                ]
            )
        assert exit_code == 0, exit_code
        report = preflight.read_json(root / "preflight-erigon.json")
        assert report["status"] == "ok", report
        assert report["selected_method"] == "trace_transaction", report
        assert len(report["checks"]) == 3, report

    print("trace_endpoint_preflight_selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
