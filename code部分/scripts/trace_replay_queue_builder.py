#!/usr/bin/env python3
"""Build a historical trace replay queue from reviewed candidate transactions."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def queue_id_for(chain: str, incident_id: str, tx_hash: str) -> str:
    seed = f"trace-replay-queue.v1:{chain}:{incident_id}:{tx_hash.lower()}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build trace replay queue from label candidates.")
    parser.add_argument("--candidates", default="data/training/replay_label_candidates.seed.json")
    parser.add_argument("--out", default="data/training/trace_replay_queue.v1.json")
    parser.add_argument("--report", default="ops/reports/trace-replay-queue-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    payload = read_json(root / args.candidates)
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for incident in payload.get("positive_candidates", []):
        chain = incident.get("chain")
        incident_id = incident.get("incident_id")
        for tx in incident.get("candidate_transactions", []):
            tx_hash = tx.get("tx_hash")
            if chain != "ethereum":
                skipped.append(
                    {
                        "incident_id": incident_id,
                        "tx_hash": tx_hash,
                        "reason": "non_ethereum_trace_replay_not_supported",
                    }
                )
                continue
            items.append(
                {
                    "queue_id": queue_id_for(chain, incident_id, tx_hash),
                    "incident_id": incident_id,
                    "chain": chain,
                    "chain_id": 1,
                    "tx_hash": tx_hash,
                    "candidate_role": tx.get("candidate_role"),
                    "confidence": tx.get("confidence"),
                    "review_status": tx.get("review_status"),
                    "preferred_rpc_methods": ["debug_traceTransaction", "trace_transaction"],
                    "promotion_required": True,
                    "source_refs": tx.get("source_refs", []),
                }
            )

    queue = {
        "schema_ver": "trace-replay-queue.v1",
        "snapshot_id": payload.get("snapshot_id"),
        "created_at": now_iso(),
        "items": sorted(items, key=lambda item: (item["incident_id"], item["tx_hash"])),
        "skipped": skipped,
        "promotion_criteria": [
            "trace replay succeeds on Ethereum mainnet",
            "trace produces non-empty calls or state diff",
            "graph replay produces rich transfer/call evidence",
            "analyst confirms transaction role before training label promotion",
        ],
    }
    write_json(root / args.out, queue)

    report = {
        "checked_at": now_iso(),
        "status": "ok" if items else "empty",
        "queue_items": len(items),
        "skipped": len(skipped),
        "out": args.out,
        "preferred_rpc_methods": ["debug_traceTransaction", "trace_transaction"],
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
