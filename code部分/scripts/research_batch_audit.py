#!/usr/bin/env python3
"""Audit a bounded Stage 8 research expansion batch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_expansion_builder import canonical_hash, held_out_hashes, read_json, write_json


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def tx_hashes(payload: dict[str, Any]) -> set[str]:
    return {str(item.get("tx_hash", "")).lower() for item in payload.get("items", [])}


def trace_attempts(report: dict[str, Any]) -> int:
    return int(report.get("rpc_call_summary", {}).get("trace_attempts", 0))


def selected_methods(report: dict[str, Any]) -> set[str]:
    return {
        str(item.get("selected"))
        for item in report.get("attempts", [])
        if item.get("selected") not in {None, "existing_bundle", "none"}
    }


def audit_batch(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    config = payloads["config"]
    builder = payloads["builder"]
    positive_queue = payloads["positive_queue"]
    negative_queue = payloads["negative_queue"]
    positive_initial = payloads["positive_initial"]
    positive_resume = payloads["positive_resume"]
    negative_trace = payloads["negative_trace"]
    raw_manifest = payloads["raw_manifest"]
    trace_audit = payloads["trace_audit"]
    quality = payloads["quality"]
    screen = payloads["screen"]
    split = payloads["split"]
    metadata_failure = payloads["metadata_failure"]
    metadata_corrected = payloads["metadata_corrected"]
    errors: list[str] = []
    warnings: list[str] = []

    expected_positive = int(config.get("positive_count", 0))
    expected_negative = int(config.get("negative_count", 0))
    expected_total = expected_positive + expected_negative
    guards = config.get("paid_call_guards", {})
    if config.get("trace_method") != "trace_transaction":
        errors.append("batch trace method mismatch")
    if not guards.get("forbid_debug_trace_transaction"):
        errors.append("debug_traceTransaction is not forbidden")
    if not guards.get("fail_fast") or not guards.get("skip_existing"):
        errors.append("fail-fast and skip-existing guards must be enabled")
    if not guards.get("stop_after_batch"):
        errors.append("stop_after_batch is not enabled")
    if not guards.get("provider_usage_limit_confirmed_by_user"):
        errors.append("provider usage limit confirmation is missing")
    if expected_total > int(config.get("max_paid_trace_calls", 0)):
        errors.append("batch item count exceeds paid trace cap")

    if builder.get("status") != "ready_for_paid_dry_run" or builder.get("errors"):
        errors.append("batch builder gate did not pass")
    if len(positive_queue.get("items", [])) != expected_positive:
        errors.append("positive queue count mismatch")
    if len(negative_queue.get("items", [])) != expected_negative:
        errors.append("negative queue count mismatch")
    if any(item.get("candidate_label") is not None for item in negative_queue.get("items", [])):
        errors.append("negative queue contains a label")

    frozen = held_out_hashes(split, "held_out_test")
    all_hashes = tx_hashes(positive_queue) | tx_hashes(negative_queue)
    overlap = sorted(all_hashes & frozen)
    if overlap:
        errors.append(f"batch overlaps frozen held-out data: {overlap}")

    if positive_initial.get("status") != "degraded":
        errors.append("initial positive transport failure is not preserved")
    if positive_initial.get("ok_trace_bundles") != 1:
        errors.append("initial positive success count mismatch")
    if positive_initial.get("rpc_call_summary", {}).get("trace_attempts") != 1:
        errors.append("initial failure should stop before a second trace")
    if positive_resume.get("status") != "ok":
        errors.append("positive resume did not complete")
    if positive_resume.get("ok_trace_bundles") != expected_positive:
        errors.append("positive resume count mismatch")
    if positive_resume.get("reused_existing_bundles") != 1:
        errors.append("positive resume did not reuse the first success")
    if negative_trace.get("status") != "ok":
        errors.append("negative trace replay did not complete")
    if negative_trace.get("ok_trace_bundles") != expected_negative:
        errors.append("negative trace count mismatch")
    for name, report in (
        ("positive_initial", positive_initial),
        ("positive_resume", positive_resume),
        ("negative_trace", negative_trace),
    ):
        if report.get("method") != "trace_transaction":
            errors.append(f"{name} method mismatch")
        unexpected = selected_methods(report) - {"trace_transaction"}
        if unexpected:
            errors.append(f"{name} selected unexpected methods: {sorted(unexpected)}")

    if metadata_failure.get("trace_calls_performed") != 0:
        errors.append("failed metadata attempt performed a trace call")
    if metadata_failure.get("status") != "insufficient_candidates":
        errors.append("metadata failure status is not preserved")
    if metadata_corrected.get("status") != "ok" or metadata_corrected.get("selected_count") != 5:
        errors.append("corrected metadata sample did not pass")

    manifest_hashes = {
        str(item.get("tx_hash", "")).lower() for item in raw_manifest.get("entries", [])
    }
    if manifest_hashes != all_hashes or raw_manifest.get("expected_transactions") != expected_total:
        errors.append("raw trace manifest does not exactly match batch queues")
    if trace_audit.get("status") != "ok" or trace_audit.get("normalized_trace_files") != expected_total:
        errors.append("trace bundle audit did not pass")
    if trace_audit.get("trace_source_counts") != {"trace_transaction": expected_total}:
        errors.append("trace bundle audit contains a non-approved source")
    if quality.get("status") != "ok" or quality.get("errors"):
        errors.append("rich graph quality audit did not pass")
    if quality.get("audited", {}).get("graphs") != expected_total:
        errors.append("rich graph count mismatch")

    if screen.get("candidate_count") != expected_negative or screen.get("screened_count") != expected_negative:
        errors.append("negative screen count mismatch")
    if screen.get("labels_promoted") != 0 or screen.get("human_review_completed") is not False:
        errors.append("negative screen incorrectly promoted or reviewed labels")
    if screen.get("known_exploit_transaction_hash_hits") or screen.get("ofac_sdn_graph_address_hits"):
        errors.append("negative screen found an external exact match")
    if screen.get("positive_anchor_overlaps"):
        errors.append("negative screen found a positive anchor overlap")

    role_graphs = sum(
        int(values.get("protocol_role_graphs", 0))
        for values in quality.get("cohort_stats", {}).values()
        if isinstance(values, dict)
    )
    if role_graphs * 4 < expected_total:
        warnings.append(
            "protocol-role coverage is below 25%; unmatched negatives remain review candidates"
        )
    if quality.get("feature_missing_flags", {}).get("context_1h_protocol_unavailable"):
        warnings.append("one-hour protocol context is unavailable for this isolated historical batch")

    complete = not errors
    return {
        "checked_at": now_iso(),
        "gate": "stage8_research_batch_round_002",
        "batch_id": config.get("batch_id"),
        "status": "batch_ok_review_pending_target_incomplete" if complete else "failed",
        "batch_complete": complete,
        "research_target_complete": False,
        "counts": {
            "positive_rich_graphs": expected_positive if complete else 0,
            "unlabeled_negative_rich_graphs": expected_negative if complete else 0,
            "hard_negative_candidates": screen.get("hard_negative_candidates", 0),
            "labels_promoted": 0,
            "protocol_role_graphs": role_graphs,
            "frozen_held_out_overlap": len(overlap),
        },
        "paid_calls": {
            "unique_trace_transactions": expected_total if complete else 0,
            "trace_transaction_attempts": trace_attempts(positive_initial)
            + trace_attempts(positive_resume)
            + trace_attempts(negative_trace),
            "reused_successful_bundles": positive_resume.get("reused_existing_bundles", 0),
            "debug_trace_transaction_attempts": 0,
        },
        "cumulative_unpromoted_pool": {
            "positive_rich_graphs": 6,
            "negative_rich_graph_candidates": 30,
            "hard_negative_candidates": 9,
        },
        "frozen_held_out_overlap": overlap,
        "provider_cost_note": "Inspect the provider billing dashboard; RPC responses do not include invoice cost.",
        "next_gate": (
            "analyst review, protocol-matched negative filtering, and versioned label promotion"
            if complete
            else None
        ),
        "warnings": warnings,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Stage 8 research batch round 002.")
    parser.add_argument("--config", default="config/research_batch.stage8.round-002.v1.json")
    parser.add_argument("--builder", default="ops/reports/research-batch-builder.stage8.round-002.latest.json")
    parser.add_argument("--positive-queue", default="data/training/research_positive_trace_queue.stage8.round-002.v1.json")
    parser.add_argument("--negative-queue", default="data/training/research_negative_trace_queue.stage8.round-002.v1.json")
    parser.add_argument("--positive-initial", default="ops/reports/research-positive-trace-replay.stage8.round-002.latest.json")
    parser.add_argument("--positive-resume", default="ops/reports/research-positive-trace-replay.stage8.round-002.resume.latest.json")
    parser.add_argument("--negative-trace", default="ops/reports/research-negative-trace-replay.stage8.round-002.latest.json")
    parser.add_argument("--raw-manifest", default="data/training/raw-trace-manifest.stage8.round-002.v1.json")
    parser.add_argument("--trace-audit", default="ops/reports/trace-bundle-audit.stage8.round-002.latest.json")
    parser.add_argument("--quality", default="ops/reports/rich-graph-quality-audit.stage8.round-002.latest.json")
    parser.add_argument("--screen", default="ops/reports/research-negative-screen.stage8.round-002.latest.json")
    parser.add_argument("--split", default="data/training/split_manifest.stage4.v1.json")
    parser.add_argument("--metadata-failure", default="ops/reports/research-negative-sampler.stage8.round-002.lendfme.latest.json")
    parser.add_argument("--metadata-corrected", default="ops/reports/research-negative-sampler.stage8.round-002.lendfme.corrected.latest.json")
    parser.add_argument("--out", default="ops/reports/research-batch-audit.stage8.round-002.latest.json")
    args = parser.parse_args()
    root = Path.cwd()
    inputs = {
        name: read_json(root / path)
        for name, path in {
            "config": args.config,
            "builder": args.builder,
            "positive_queue": args.positive_queue,
            "negative_queue": args.negative_queue,
            "positive_initial": args.positive_initial,
            "positive_resume": args.positive_resume,
            "negative_trace": args.negative_trace,
            "raw_manifest": args.raw_manifest,
            "trace_audit": args.trace_audit,
            "quality": args.quality,
            "screen": args.screen,
            "split": args.split,
            "metadata_failure": args.metadata_failure,
            "metadata_corrected": args.metadata_corrected,
        }.items()
    }
    report = audit_batch(inputs)
    report["input_content_hash"] = canonical_hash(inputs)
    write_json(root / args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
