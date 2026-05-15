# Phase 4-C Replay Label Candidates Report

## Summary

Added a candidate label backlog for exploit replay and normal complex transaction
sampling. This reduces the manual search work needed before GraphSAGE training,
but does not make the model training-ready until trace replay and analyst review
are complete.

## Artifacts

- `data/training/replay_label_candidates.seed.json`
- `scripts/replay_label_candidates_check.py`
- `scripts/trace_replay_queue_builder.py`
- `scripts/historical_trace_replay.py`
- `ops/replay_label_candidates_runbook.md`
- `ops/trace_replay_queue_runbook.md`
- `ops/historical_trace_replay_runbook.md`
- `ops/reports/replay-label-candidates-check.latest.json`
- `data/training/trace_replay_queue.v1.json`
- `ops/reports/trace-replay-queue-builder.latest.json`
- `ops/reports/historical-trace-replay.latest.json`

## Current Limits

- Candidate transaction hashes are not promoted to confirmed labels.
- All Ethereum seed incidents now have at least one candidate transaction hash.
- Mango Markets is non-Ethereum and remains out of current Ethereum trace replay scope.
- Normal complex candidate sampling is seeded in
  `data/training/normal_replay_candidates.seed.json`; those samples still
  require trace replay, screening, and analyst promotion before training.
