#!/usr/bin/env python3
"""Build normal transaction replay candidates from provider-only pending captures."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
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


def iter_json_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.json"))


def queue_id_for(tx_hash: str, label: str = "normal_candidate") -> str:
    seed = f"normal-replay-candidate.v1:{label}:{tx_hash.lower()}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def positive_hashes(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = read_json(path)
    hashes: set[str] = set()
    for incident in payload.get("positive_candidates", []):
        for tx in incident.get("candidate_transactions", []):
            tx_hash = tx.get("tx_hash")
            if isinstance(tx_hash, str):
                hashes.add(tx_hash.lower())
    return hashes


def protocol_roles(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = read_json(path)
    roles = {}
    for contract in payload.get("contracts", []):
        address = contract.get("address")
        if isinstance(address, str):
            roles[address.lower()] = contract
    return roles


def classify_tx(tx: dict[str, Any], roles_by_address: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    to_address = (tx.get("to") or "").lower()
    input_data = tx.get("input") if isinstance(tx.get("input"), str) else "0x"
    selector = input_data[:10] if input_data and input_data != "0x" else None
    role = roles_by_address.get(to_address)
    if role:
        return "whitelisted_protocol_call", {
            "protocol_id": role.get("protocol_id"),
            "protocol_category": role.get("category"),
            "contract": role.get("contract"),
            "selector": selector,
        }
    if input_data == "0x":
        return "simple_transfer", {"selector": None}
    if selector == "0xa9059cbb":
        return "erc20_transfer", {"selector": selector}
    if selector == "0x095ea7b3":
        return "erc20_approve", {"selector": selector}
    return "contract_call", {"selector": selector}


def select_round_robin(groups: dict[str, list[dict[str, Any]]], target_count: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    group_names = sorted(groups)
    index = 0
    while len(selected) < target_count:
        progressed = False
        for name in group_names:
            items = groups[name]
            if index < len(items):
                selected.append(items[index])
                progressed = True
                if len(selected) >= target_count:
                    break
        if not progressed:
            break
        index += 1
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Build normal replay candidate set.")
    parser.add_argument("--pending-input", default="data/replay/pending-tx.v1")
    parser.add_argument("--positive-candidates", default="data/training/replay_label_candidates.seed.json")
    parser.add_argument("--protocol-roles", default="config/protocol_roles.json")
    parser.add_argument("--target-count", type=int, default=50)
    parser.add_argument("--out", default="data/training/normal_replay_candidates.seed.json")
    parser.add_argument("--queue-out", default="data/training/normal_trace_replay_queue.v1.json")
    parser.add_argument("--report", default="ops/reports/normal-replay-candidates-builder.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    excluded_hashes = positive_hashes(root / args.positive_candidates)
    roles_by_address = protocol_roles(root / args.protocol_roles)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_hashes: set[str] = set()
    skipped = defaultdict(int)

    for path in iter_json_files(root / args.pending_input):
        event = read_json(path)
        tx = event.get("tx")
        if not isinstance(tx, dict):
            skipped["missing_tx_object"] += 1
            continue
        tx_hash = tx.get("hash") or event.get("tx_hash")
        if not isinstance(tx_hash, str):
            skipped["missing_tx_hash"] += 1
            continue
        tx_hash_lower = tx_hash.lower()
        if tx_hash_lower in seen_hashes:
            skipped["duplicate_tx_hash"] += 1
            continue
        if tx_hash_lower in excluded_hashes:
            skipped["positive_candidate_hash"] += 1
            continue
        if tx.get("blockNumber") is None:
            skipped["not_mined_at_capture_time"] += 1
            continue
        seen_hashes.add(tx_hash_lower)
        kind, metadata = classify_tx(tx, roles_by_address)
        groups[kind].append(
            {
                "queue_id": queue_id_for(tx_hash),
                "incident_id": "normal_candidate",
                "chain": "ethereum",
                "chain_id": 1,
                "tx_hash": tx_hash_lower,
                "candidate_label": 0,
                "candidate_role": "normal_candidate",
                "review_status": "needs_trace_replay_and_screening",
                "selection_bucket": kind,
                "block_number": tx.get("blockNumber"),
                "to": tx.get("to"),
                "from": tx.get("from"),
                "value": tx.get("value"),
                "gas": tx.get("gas"),
                "metadata": metadata,
                "source_event_id": event.get("event_id"),
                "source_replay_path": str(path.relative_to(root)),
                "preferred_rpc_methods": ["debug_traceTransaction", "trace_transaction"],
                "promotion_required": True,
            }
        )

    selected = select_round_robin(groups, args.target_count)
    candidates = {
        "schema_ver": "normal-replay-candidates.v1",
        "created_at": now_iso(),
        "candidate_label": 0,
        "review_status": "needs_trace_replay_and_screening",
        "target_count": args.target_count,
        "selection_rules": [
            "ethereum mainnet only",
            "transaction was mined at capture time",
            "exclude known positive exploit candidate hashes",
            "dedupe by tx_hash",
            "sample across simple transfers, ERC20 transfers, approvals, whitelisted protocol calls, and other contract calls",
            "promote only after trace replay and analyst screening",
        ],
        "items": selected,
    }
    write_json(root / args.out, candidates)

    queue = {
        "schema_ver": "trace-replay-queue.v1",
        "snapshot_id": "normal-candidates.seed-2026-05-14",
        "created_at": now_iso(),
        "items": selected,
        "skipped": [],
        "promotion_criteria": [
            "trace replay succeeds on Ethereum mainnet",
            "trace produces non-empty calls or state diff when applicable",
            "transaction is not linked to known incidents, sanctions, exploit labels, or suspicious public reports",
            "analyst confirms normal_candidate role before negative-label promotion",
        ],
    }
    write_json(root / args.queue_out, queue)

    report = {
        "checked_at": now_iso(),
        "status": "ok" if len(selected) >= args.target_count else "degraded",
        "target_count": args.target_count,
        "selected_count": len(selected),
        "available_by_bucket": {name: len(items) for name, items in sorted(groups.items())},
        "selected_by_bucket": dict(sorted({name: sum(1 for item in selected if item["selection_bucket"] == name) for name in groups}.items())),
        "skipped": dict(sorted(skipped.items())),
        "out": args.out,
        "queue_out": args.queue_out,
    }
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
