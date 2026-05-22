# Normal Replay Candidates Runbook

## Purpose

Build and validate a normal transaction candidate backlog for future negative
label promotion. These candidates are not confirmed negatives until trace replay
and analyst screening are complete.

## Build

```bash
python3 scripts/normal_replay_candidates_builder.py \
  --pending-input data/replay/pending-tx.v1 \
  --positive-candidates data/training/replay_label_candidates.seed.json \
  --target-count 50 \
  --out data/training/normal_replay_candidates.seed.json \
  --queue-out data/training/normal_trace_replay_queue.v1.json \
  --report ops/reports/normal-replay-candidates-builder.latest.json
```

## Check

```bash
python3 scripts/normal_replay_candidates_check.py \
  --candidates data/training/normal_replay_candidates.seed.json \
  --queue data/training/normal_trace_replay_queue.v1.json \
  --positive-candidates data/training/replay_label_candidates.seed.json \
  --min-count 50 \
  --out ops/reports/normal-replay-candidates-check.latest.json
```
