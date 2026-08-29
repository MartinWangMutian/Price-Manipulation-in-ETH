#!/usr/bin/env python3
"""Generate provider-only fallback TraceBundle records.

Provider-only mode cannot rely on local Geth `debug_traceCall` or Erigon
`trace_call`. This script turns PendingTxEvent replay records into lightweight
TraceBundle records with `trace_status=unsupported`, preserving the pipeline
contract for later graph and alert stages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def event_id_for(chain_id: int, tx_hash: str, source: str) -> str:
    seed = f"trace-bundle.v1:{chain_id}:{tx_hash}:{source}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def replay_path(root: Path, created_at: datetime, event_id: str) -> Path:
    date_part = created_at.strftime("%Y-%m-%d")
    hour_part = created_at.strftime("%H")
    return (
        root
        / "data"
        / "replay"
        / "trace-bundle.v1"
        / f"dt={date_part}"
        / f"hour={hour_part}"
        / f"{event_id}.json"
    )


def build_trace_bundle(pending_event: dict[str, Any]) -> dict[str, Any]:
    created = now_dt()
    chain_id = pending_event["chain_id"]
    tx_hash = pending_event["tx_hash"]
    trace_source = "provider_fallback"
    event_id = event_id_for(chain_id, tx_hash, trace_source)
    return {
        "event_id": event_id,
        "schema_ver": "trace-bundle.v1",
        "chain_id": chain_id,
        "created_at": created.isoformat(timespec="milliseconds"),
        "observed_at": pending_event.get("seen_at") or pending_event.get("created_at"),
        "idempotency_key": f"{chain_id}:{tx_hash}:{trace_source}",
        "tx_hash": tx_hash,
        "trace_source": trace_source,
        "trace_status": "unsupported",
        "trace_error": {
            "code": "provider_only_trace_unavailable",
            "message": (
                "Provider-only mode does not expose local debug_traceCall "
                "or trace_call for pending transaction simulation."
            ),
            "upstream_event_id": pending_event["event_id"],
            "raw_tx_status": pending_event.get("raw_tx_status"),
        },
        "calls": [],
        "logs": [],
        "token_transfers": [],
        "state_diff": {},
        "raw_trace_ref": None,
    }


def validate_trace_bundle(bundle: dict[str, Any]) -> list[str]:
    required = {
        "event_id",
        "schema_ver",
        "chain_id",
        "created_at",
        "idempotency_key",
        "tx_hash",
        "trace_source",
        "trace_status",
        "calls",
        "logs",
        "state_diff",
    }
    errors = []
    missing = sorted(required - set(bundle))
    if missing:
        errors.append(f"missing required fields: {missing}")
    if bundle.get("schema_ver") != "trace-bundle.v1":
        errors.append("schema_ver must be trace-bundle.v1")
    if bundle.get("trace_source") != "provider_fallback":
        errors.append("trace_source must be provider_fallback")
    if bundle.get("trace_status") != "unsupported":
        errors.append("trace_status must be unsupported")
    for field in ("calls", "logs"):
        if not isinstance(bundle.get(field), list):
            errors.append(f"{field} must be a list")
    if not isinstance(bundle.get("state_diff"), dict):
        errors.append("state_diff must be an object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/replay/pending-tx.v1",
        help="pending-tx replay root",
    )
    parser.add_argument(
        "--summary-out",
        default="ops/reports/trace-fallback.latest.json",
        help="summary report path",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    files = sorted((root / args.input).glob("dt=*/hour=*/*.json"))
    written = []
    errors: list[dict[str, Any]] = []

    for pending_path in files:
        try:
            pending_event = json.loads(pending_path.read_text(encoding="utf-8"))
            bundle = build_trace_bundle(pending_event)
        except (KeyError, json.JSONDecodeError) as exc:
            errors.append(
                {"path": str(pending_path.relative_to(root)), "errors": [str(exc)]}
            )
            continue

        validation_errors = validate_trace_bundle(bundle)
        if validation_errors:
            errors.append(
                {
                    "path": str(pending_path.relative_to(root)),
                    "tx_hash": pending_event.get("tx_hash"),
                    "errors": validation_errors,
                }
            )
            continue

        output_path = replay_path(root, now_dt(), bundle["event_id"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
        written.append(
            {
                "event_id": bundle["event_id"],
                "tx_hash": bundle["tx_hash"],
                "trace_status": bundle["trace_status"],
                "replay_path": str(output_path.relative_to(root)),
            }
        )

    summary = {
        "checked_at": now_dt().isoformat(timespec="milliseconds"),
        "input": args.input,
        "pending_files_seen": len(files),
        "written_trace_bundles": len(written),
        "trace_status": "unsupported",
        "written": written,
        "errors": errors,
        "status": "ok" if written and not errors else "degraded",
    }
    out_path = root / args.summary_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
