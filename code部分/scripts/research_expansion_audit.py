#!/usr/bin/env python3
"""Audit the Stage 8 research expansion pilot and frozen-test isolation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_expansion_builder import canonical_hash, held_out_hashes, read_json, write_json


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def item_hashes(payload: dict[str, Any]) -> set[str]:
    return {str(item.get("tx_hash", "")).lower() for item in payload.get("items", [])}


def audit_payloads(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    config = payloads["config"]
    index = payloads["index"]
    full_positive = payloads["full_positive"]
    pilot_positive = payloads["pilot_positive"]
    pilot_negative = payloads["pilot_negative"]
    sampler = payloads["sampler"]
    positive_trace = payloads["positive_trace"]
    negative_trace = payloads["negative_trace"]
    raw_manifest = payloads["raw_manifest"]
    quality = payloads["quality"]
    screen = payloads["screen"]
    split = payloads["split"]
    failed_sampler = payloads.get("failed_sampler", {})
    errors: list[str] = []

    if config.get("trace_method") != "trace_transaction":
        errors.append("config trace method is not trace_transaction")
    if not config.get("paid_call_guards", {}).get("forbid_debug_trace_transaction"):
        errors.append("debug_traceTransaction is not explicitly forbidden")
    if index.get("status") not in {"ready_for_pilot", "complete"}:
        errors.append(f"expansion index status is {index.get('status')}")
    progress = index.get("progress", {})
    targets = config["targets"]
    if progress.get("verified_independent_events", 0) < targets["independent_attack_events"]:
        errors.append("verified independent-event target is not met")

    for name, queue in (
        ("full_positive", full_positive),
        ("pilot_positive", pilot_positive),
        ("pilot_negative", pilot_negative),
    ):
        if queue.get("trace_method") != "trace_transaction":
            errors.append(f"{name} queue trace method mismatch")
        for item in queue.get("items", []):
            if item.get("preferred_rpc_methods") != ["trace_transaction"]:
                errors.append(f"{name} queue item allows a non-approved trace method")

    expected_positive = config["paid_call_guards"]["pilot_positive_count"]
    expected_negative = config["paid_call_guards"]["pilot_negative_count"]
    if len(pilot_positive.get("items", [])) != expected_positive:
        errors.append("pilot positive queue count mismatch")
    if len(pilot_negative.get("items", [])) != expected_negative:
        errors.append("pilot negative queue count mismatch")
    if any(item.get("candidate_label") is not None for item in pilot_negative.get("items", [])):
        errors.append("negative candidates were assigned labels before screening")

    frozen = held_out_hashes(split, config["split_policy"]["held_out_split"])
    new_hashes = item_hashes(full_positive) | item_hashes(pilot_negative)
    overlap = sorted(frozen & new_hashes)
    if overlap:
        errors.append(f"new Stage 8 data overlaps frozen held-out data: {overlap}")

    if sampler.get("status") != "ok" or sampler.get("selected_count") != expected_negative:
        errors.append("corrected negative metadata sampler did not complete")
    if sampler.get("trace_calls_performed") != 0:
        errors.append("metadata sampler unexpectedly performed trace calls")
    if failed_sampler:
        if failed_sampler.get("trace_calls_performed") != 0:
            errors.append("failed metadata attempt performed trace calls")
        if failed_sampler.get("status") != "failed_stopped":
            errors.append("failed metadata attempt was not recorded as stopped")

    for name, report, expected in (
        ("positive", positive_trace, expected_positive),
        ("negative", negative_trace, expected_negative),
    ):
        if report.get("status") != "ok":
            errors.append(f"{name} trace replay status is {report.get('status')}")
        if report.get("method") != "trace_transaction":
            errors.append(f"{name} trace replay method mismatch")
        if report.get("ok_trace_bundles") != expected or report.get("failed_trace_bundles") != 0:
            errors.append(f"{name} trace replay count mismatch")
        if any(item.get("selected") != "trace_transaction" for item in report.get("attempts", [])):
            errors.append(f"{name} trace replay selected an unexpected method")

    pilot_hashes = item_hashes(pilot_positive) | item_hashes(pilot_negative)
    raw_hashes = {
        str(item.get("tx_hash", "")).lower() for item in raw_manifest.get("entries", [])
    }
    if raw_hashes != pilot_hashes:
        errors.append("raw trace manifest does not exactly match pilot queues")
    if raw_manifest.get("expected_transactions") != expected_positive + expected_negative:
        errors.append("raw trace manifest count mismatch")

    if quality.get("status") != "ok" or quality.get("errors"):
        errors.append("pilot rich graph quality audit is not clean")
    audited = quality.get("audited", {})
    if audited.get("graphs") != expected_positive + expected_negative:
        errors.append("pilot graph count mismatch")
    if quality.get("expected", {}).get("exploit_graphs") != expected_positive:
        errors.append("pilot exploit graph count mismatch")
    if quality.get("expected", {}).get("normal_graphs") != expected_negative:
        errors.append("pilot candidate graph count mismatch")

    if screen.get("candidate_label") is not None:
        errors.append("negative screen assigned a cohort label")
    if screen.get("human_review_completed") is not False:
        errors.append("negative screen incorrectly claims human review")
    screen_items = screen.get("items", [])
    if len(screen_items) != expected_negative:
        errors.append("negative screen count mismatch")
    if any(item.get("candidate_label") is not None for item in screen_items):
        errors.append("negative screen item assigned a label")
    if any(item.get("positive_anchor_overlap") for item in screen_items):
        errors.append("negative candidate overlaps a positive anchor")

    pilot_complete = not errors
    target_complete = bool(index.get("research_target_complete"))
    if target_complete:
        status = "complete" if pilot_complete else "failed"
    else:
        status = "pilot_ok_target_incomplete" if pilot_complete else "failed"
    return {
        "checked_at": now_iso(),
        "gate": "stage8_research_expansion_pilot",
        "status": status,
        "pilot_complete": pilot_complete,
        "research_target_complete": target_complete,
        "verified_event_target_met": progress.get("verified_independent_events", 0)
        >= targets["independent_attack_events"],
        "positive_graph_target_met": progress.get("current_promoted_positive_rich_graphs", 0)
        >= targets["positive_rich_graphs"],
        "negative_graph_target_met": progress.get("current_promoted_negative_rich_graphs", 0)
        >= targets["negative_rich_graphs"],
        "progress": progress,
        "pilot": {
            "positive_trace_graphs": expected_positive,
            "unlabeled_negative_trace_graphs": expected_negative,
            "trace_transaction_attempts": positive_trace.get("rpc_call_summary", {}).get(
                "trace_attempts", 0
            )
            + negative_trace.get("rpc_call_summary", {}).get("trace_attempts", 0),
            "hard_negative_candidates": sum(
                bool(item.get("hard_negative_candidate")) for item in screen_items
            ),
            "negative_candidates_requiring_human_review": sum(
                item.get("review_status") == "screen_pass_human_review_required"
                for item in screen_items
            ),
            "labels_promoted": 0,
            "metadata_sampler_rpc_attempts": sampler.get("rpc_call_attempts"),
            "wide_sampler_attempt_stopped_before_trace": bool(failed_sampler),
        },
        "frozen_held_out_count": len(frozen),
        "frozen_held_out_overlap": overlap,
        "provider_cost_note": "Inspect the provider billing dashboard; JSON-RPC responses do not include invoice cost.",
        "stop_reason": (
            "paid pilot completed; stop_after_pilot is enabled and research graph targets remain unmet"
            if pilot_complete and not target_complete
            else None
        ),
        "next_gate": (
            "human-review the five candidates, inspect provider cost, expand protocol-role coverage, then authorize the next versioned batch"
            if not target_complete
            else "stage9_formal_experiments"
        ),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Stage 8 research expansion pilot.")
    parser.add_argument("--config", default="config/research_expansion.stage8.v1.json")
    parser.add_argument("--index", default="data/training/research_expansion_index.stage8.v1.json")
    parser.add_argument("--full-positive", default="data/training/research_positive_trace_queue.stage8.v1.json")
    parser.add_argument("--pilot-positive", default="data/training/research_pilot_positive_trace_queue.stage8.v1.json")
    parser.add_argument("--pilot-negative", default="data/training/research_pilot_negative_trace_queue.stage8.v1.json")
    parser.add_argument("--sampler", default="ops/reports/research-negative-sampler.stage8.pilot.latest.json")
    parser.add_argument("--failed-sampler", default="ops/reports/research-negative-sampler.stage8.attempt-001.json")
    parser.add_argument("--positive-trace", default="ops/reports/research-positive-trace-replay.stage8.pilot.latest.json")
    parser.add_argument("--negative-trace", default="ops/reports/research-negative-trace-replay.stage8.pilot.latest.json")
    parser.add_argument("--raw-manifest", default="data/training/raw-trace-manifest.stage8.pilot.v1.json")
    parser.add_argument("--quality", default="ops/reports/rich-graph-quality-audit.stage8.pilot.latest.json")
    parser.add_argument("--screen", default="data/training/research_negative_screen.stage8.pilot.v1.json")
    parser.add_argument("--split", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--out", default="ops/reports/research-expansion-audit.stage8.latest.json")
    args = parser.parse_args()
    root = Path.cwd()
    inputs = {
        key: read_json(root / value)
        for key, value in {
            "config": args.config,
            "index": args.index,
            "full_positive": args.full_positive,
            "pilot_positive": args.pilot_positive,
            "pilot_negative": args.pilot_negative,
            "sampler": args.sampler,
            "failed_sampler": args.failed_sampler,
            "positive_trace": args.positive_trace,
            "negative_trace": args.negative_trace,
            "raw_manifest": args.raw_manifest,
            "quality": args.quality,
            "screen": args.screen,
            "split": args.split,
        }.items()
    }
    report = audit_payloads(inputs)
    report["input_content_hash"] = canonical_hash(inputs)
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
