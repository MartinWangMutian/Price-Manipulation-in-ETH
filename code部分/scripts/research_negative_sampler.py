#!/usr/bin/env python3
"""Sample Stage 8 unlabeled negative candidates near a verified incident."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from historical_trace_replay import rpc_call
from research_expansion_builder import held_out_hashes, read_json, valid_tx_hash, write_json


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def hex_int(value: Any) -> int:
    if not isinstance(value, str):
        return 0
    try:
        return int(value, 16)
    except ValueError:
        return 0


def input_bytes(tx: dict[str, Any]) -> int:
    value = tx.get("input")
    if not isinstance(value, str) or not value.startswith("0x"):
        return 0
    return max(0, (len(value) - 2) // 2)


def closeness(left: int, right: int) -> float:
    return 1.0 / (1.0 + abs(math.log1p(max(0, left)) - math.log1p(max(0, right))))


def metadata_score(candidate: dict[str, Any], anchor: dict[str, Any]) -> float:
    gas_score = closeness(hex_int(candidate.get("gas")), hex_int(anchor.get("gas")))
    input_score = closeness(input_bytes(candidate), input_bytes(anchor))
    value_score = closeness(hex_int(candidate.get("value")), hex_int(anchor.get("value")))
    offset_score = 1.0 / (1.0 + abs(int(candidate.get("block_offset", 0))) / 10000.0)
    contract_score = 1.0 if candidate.get("to") and input_bytes(candidate) else 0.0
    return round(
        0.25 * gas_score
        + 0.20 * input_score
        + 0.10 * value_score
        + 0.20 * offset_score
        + 0.25 * contract_score,
        8,
    )


def tie_breaker(seed: int, tx_hash: str) -> str:
    return hashlib.sha256(f"{seed}:{tx_hash.lower()}".encode("utf-8")).hexdigest()


def select_candidates(
    transactions: list[dict[str, Any]],
    anchor: dict[str, Any],
    excluded_hashes: set[str],
    excluded_addresses: set[str],
    minimum_contract_gas: int,
    target_count: int,
    seed: int,
    max_per_to_address: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    skipped = {
        "invalid_hash": 0,
        "excluded_hash": 0,
        "excluded_address": 0,
        "not_contract_call": 0,
        "gas_below_minimum": 0,
        "duplicate_hash": 0,
        "to_address_cap": 0,
    }
    seen: set[str] = set()
    eligible: list[dict[str, Any]] = []
    for tx in transactions:
        tx_hash = str(tx.get("hash", "")).lower()
        if not valid_tx_hash(tx_hash):
            skipped["invalid_hash"] += 1
            continue
        if tx_hash in seen:
            skipped["duplicate_hash"] += 1
            continue
        seen.add(tx_hash)
        if tx_hash in excluded_hashes:
            skipped["excluded_hash"] += 1
            continue
        endpoints = {str(tx.get("from", "")).lower(), str(tx.get("to", "")).lower()}
        if endpoints & excluded_addresses:
            skipped["excluded_address"] += 1
            continue
        if not tx.get("to") or input_bytes(tx) == 0:
            skipped["not_contract_call"] += 1
            continue
        if hex_int(tx.get("gas")) < minimum_contract_gas:
            skipped["gas_below_minimum"] += 1
            continue
        item = dict(tx)
        item["metadata_match_score"] = metadata_score(item, anchor)
        eligible.append(item)

    eligible.sort(
        key=lambda item: (
            -float(item["metadata_match_score"]),
            tie_breaker(seed, item["hash"]),
        )
    )
    selected: list[dict[str, Any]] = []
    per_to: dict[str, int] = {}
    for item in eligible:
        to_address = str(item.get("to", "")).lower()
        if per_to.get(to_address, 0) >= max_per_to_address:
            skipped["to_address_cap"] += 1
            continue
        selected.append(item)
        per_to[to_address] = per_to.get(to_address, 0) + 1
        if len(selected) >= target_count:
            break
    return selected, skipped


def rpc_with_retry(
    url: str, method: str, params: list[Any], timeout_s: float, retries: int = 1
) -> tuple[Any | None, list[dict[str, Any]]]:
    attempts = []
    for index in range(retries + 1):
        response, latency_ms = rpc_call(url, method, params, timeout_s)
        ok = "result" in response and "error" not in response and response.get("result") is not None
        attempt: dict[str, Any] = {
            "method": method,
            "attempt": index + 1,
            "ok": ok,
            "latency_ms": round(latency_ms, 2),
        }
        if not ok:
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            attempt["error"] = {"code": error.get("code"), "message": error.get("message")}
        attempts.append(attempt)
        if ok:
            return response.get("result"), attempts
    return None, attempts


def incident_by_id(payload: dict[str, Any], incident_id: str) -> dict[str, Any]:
    matches = [item for item in payload.get("incidents", []) if item.get("incident_id") == incident_id]
    if len(matches) != 1:
        raise ValueError(f"expected one incident named {incident_id}, found {len(matches)}")
    if matches[0].get("status") != "verified_anchor":
        raise ValueError(f"incident {incident_id} is not a verified anchor")
    return matches[0]


def queue_id_for(snapshot_id: str, incident_id: str, tx_hash: str) -> str:
    return hashlib.sha256(
        f"{snapshot_id}:negative:{incident_id}:{tx_hash.lower()}".encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample Stage 8 negative candidates from mainnet blocks.")
    parser.add_argument("--config", default="config/research_expansion.stage8.v1.json")
    parser.add_argument("--incidents", default="data/training/research_incidents.stage8.v1.json")
    parser.add_argument("--split-manifest", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--incident-id")
    parser.add_argument("--target-count", type=int)
    parser.add_argument("--max-blocks", type=int)
    parser.add_argument("--rpc-url", default=os.environ.get("ETH_MAIN_HTTP_URL"))
    parser.add_argument("--timeout-s", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="data/training/research_negative_candidates.stage8.pilot.v1.json")
    parser.add_argument("--queue-out", default="data/training/research_pilot_negative_trace_queue.stage8.v1.json")
    parser.add_argument("--report", default="ops/reports/research-negative-sampler.stage8.pilot.latest.json")
    args = parser.parse_args()

    root = Path.cwd()
    config = read_json(root / args.config)
    incidents_payload = read_json(root / args.incidents)
    split_manifest = read_json(root / args.split_manifest)
    incident_id = args.incident_id or config["pilot"]["incident_id"]
    target_count = (
        args.target_count
        if args.target_count is not None
        else config["paid_call_guards"]["pilot_negative_count"]
    )
    max_blocks = args.max_blocks if args.max_blocks is not None else config["pilot"]["max_blocks"]
    if target_count < 1 or max_blocks < 1:
        parser.error("--target-count and --max-blocks must be positive")
    incident = incident_by_id(incidents_payload, incident_id)
    anchor_hash = str(incident["anchor_transactions"][0]).lower()
    offsets = list(config["pilot"]["negative_block_offsets"])[:max_blocks]
    exclusion_window = config["negative_sampling"]["incident_exclusion_window_blocks"]
    if any(abs(int(offset)) <= exclusion_window for offset in offsets):
        parser.error("negative block offsets must remain outside the incident exclusion window")

    frozen_hashes = held_out_hashes(split_manifest, config["split_policy"]["held_out_split"])
    positive_hashes = {
        str(value).lower()
        for item in incidents_payload.get("incidents", [])
        for value in item.get("anchor_transactions", [])
    }
    excluded_hash_set = frozen_hashes | positive_hashes
    excluded_addresses = {
        str(value).lower()
        for item in incidents_payload.get("incidents", [])
        for value in item.get("known_attack_addresses", [])
        if isinstance(value, str)
    }
    created_at = now_iso()
    attempts: list[dict[str, Any]] = []
    block_summaries: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    anchor_block: int | None = None
    status = "dry_run_ok" if args.dry_run else "ok"
    errors: list[str] = []

    if not args.dry_run:
        if not args.rpc_url:
            status = "missing_endpoint"
            errors.append("ETH_MAIN_HTTP_URL is not configured")
        else:
            chain_id, chain_attempts = rpc_with_retry(args.rpc_url, "eth_chainId", [], args.timeout_s)
            attempts.extend(chain_attempts)
            if chain_id != "0x1":
                status = "wrong_chain"
                errors.append(f"Ethereum mainnet required, received {chain_id}")
            else:
                anchor, anchor_attempts = rpc_with_retry(
                    args.rpc_url, "eth_getTransactionByHash", [anchor_hash], args.timeout_s
                )
                attempts.extend(anchor_attempts)
                if not isinstance(anchor, dict) or str(anchor.get("hash", "")).lower() != anchor_hash:
                    status = "failed"
                    errors.append("anchor transaction was not found or mismatched")
                else:
                    anchor_block = hex_int(anchor.get("blockNumber"))
                    excluded_addresses.update(
                        value
                        for value in (
                            str(anchor.get("from", "")).lower(),
                            str(anchor.get("to", "")).lower(),
                        )
                        if value.startswith("0x") and len(value) == 42
                    )
                    transactions: list[dict[str, Any]] = []
                    for offset in offsets:
                        block_number = anchor_block + int(offset)
                        block, block_attempts = rpc_with_retry(
                            args.rpc_url,
                            "eth_getBlockByNumber",
                            [hex(block_number), True],
                            args.timeout_s,
                        )
                        attempts.extend(block_attempts)
                        if not isinstance(block, dict) or not isinstance(block.get("transactions"), list):
                            errors.append(f"failed to load candidate block {block_number}")
                            status = "failed"
                            break
                        block_transactions = block["transactions"]
                        block_summaries.append(
                            {
                                "block_number": block_number,
                                "block_hash": block.get("hash"),
                                "block_offset": int(offset),
                                "transactions": len(block_transactions),
                            }
                        )
                        for tx in block_transactions:
                            if isinstance(tx, dict):
                                transactions.append(
                                    {
                                        **tx,
                                        "block_number": block_number,
                                        "block_hash": block.get("hash"),
                                        "block_offset": int(offset),
                                    }
                                )
                    if status == "ok":
                        selected, skipped = select_candidates(
                            transactions,
                            anchor,
                            excluded_hash_set,
                            excluded_addresses,
                            config["pilot"]["minimum_contract_gas"],
                            target_count,
                            config["pilot"]["selection_seed"],
                            config["pilot"].get("max_per_to_address", 1),
                        )
                        if len(selected) < target_count:
                            status = "insufficient_candidates"
                            errors.append(f"selected {len(selected)}/{target_count} candidates")

    items = []
    for tx in selected:
        tx_hash = str(tx["hash"]).lower()
        items.append(
            {
                "queue_id": queue_id_for(config["snapshot_id"], incident_id, tx_hash),
                "incident_id": f"negative_match:{incident_id}",
                "matched_incident_id": incident_id,
                "chain": "ethereum",
                "chain_id": 1,
                "tx_hash": tx_hash,
                "candidate_label": None,
                "candidate_role": "research_negative_candidate",
                "review_status": "needs_trace_and_human_negative_screening",
                "selection_bucket": "time_gas_input_value_matched_contract_call",
                "metadata_match_score": tx["metadata_match_score"],
                "block_number": tx["block_number"],
                "block_hash": tx["block_hash"],
                "block_offset": tx["block_offset"],
                "from": tx.get("from"),
                "to": tx.get("to"),
                "gas": tx.get("gas"),
                "value": tx.get("value"),
                "input_bytes": input_bytes(tx),
                "protocol_match_status": "pending_trace_role_enrichment",
                "complexity_match_status": "pending_trace_graph",
                "preferred_rpc_methods": ["trace_transaction"],
                "promotion_required": True,
            }
        )

    candidates_payload = {
        "schema_ver": "research-negative-candidates.stage8.v1",
        "snapshot_id": f"{config['snapshot_id']}.negative-pilot",
        "created_at": created_at,
        "candidate_label": None,
        "matched_incident_id": incident_id,
        "anchor_tx_hash": anchor_hash,
        "anchor_block": anchor_block,
        "incident_exclusion_window_blocks": exclusion_window,
        "items": items,
    }
    queue = {
        "schema_ver": config["versions"]["queue_schema"],
        "snapshot_id": f"{config['snapshot_id']}.negative-pilot",
        "created_at": created_at,
        "trace_method": "trace_transaction",
        "items": items,
        "skipped": [],
        "promotion_criteria": [
            "trace_transaction and rich graph complete successfully",
            "candidate is outside every incident exclusion window",
            "candidate is not linked to known attacks, sanctions, or suspicious reports",
            "analyst confirms a legitimate complex transaction before label promotion",
        ],
    }
    report = {
        "checked_at": created_at,
        "gate": "stage8_negative_metadata_pilot",
        "status": status,
        "dry_run": args.dry_run,
        "incident_id": incident_id,
        "anchor_tx_hash": anchor_hash,
        "anchor_block": anchor_block,
        "target_count": target_count,
        "selected_count": len(items),
        "blocks_requested": len(offsets),
        "blocks_loaded": len(block_summaries),
        "block_summaries": block_summaries,
        "excluded_positive_hashes": len(positive_hashes),
        "excluded_frozen_held_out_hashes": len(frozen_hashes),
        "excluded_addresses": len(excluded_addresses),
        "skipped": skipped,
        "rpc_call_attempts": len(attempts),
        "rpc_calls_ok": sum(1 for item in attempts if item.get("ok") is True),
        "max_retries": 1,
        "trace_calls_performed": 0,
        "provider_cost_note": "Inspect the provider billing dashboard; JSON-RPC responses do not include invoice cost.",
        "errors": errors,
    }
    write_json(root / args.out, candidates_payload)
    write_json(root / args.queue_out, queue)
    write_json(root / args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status in {"ok", "dry_run_ok"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
