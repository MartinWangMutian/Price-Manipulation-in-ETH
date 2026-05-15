# Phase 4-D Normal Replay Candidates Report

## Summary

Added a normal transaction candidate backlog from provider-only pending captures.
The set is intentionally not promoted to confirmed negative labels.

## Artifacts

- `data/training/normal_replay_candidates.seed.json`
- `data/training/normal_trace_replay_queue.v1.json`
- `scripts/normal_replay_candidates_builder.py`
- `scripts/normal_replay_candidates_check.py`
- `ops/normal_replay_candidates_runbook.md`
- `ops/reports/normal-replay-candidates-builder.latest.json`
- `ops/reports/normal-replay-candidates-check.latest.json`

## Current Candidate Mix

- Total: 50
- Contract calls: 16
- ERC20 transfers: 16
- Simple transfers: 15
- ERC20 approvals: 3

## Promotion Criteria

- Historical trace replay succeeds.
- The transaction is screened against positive exploit labels and suspicious
  public incident reports.
- Rich graph features are available for model training.
- Analyst confirms the `normal_candidate` role before negative-label promotion.
