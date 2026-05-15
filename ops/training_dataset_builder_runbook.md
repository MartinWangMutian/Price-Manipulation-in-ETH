# Training Dataset Builder Runbook

## Purpose

Build seed Phase 4-B dataset manifests from public incident labels and current replay graphs.

## Command

```bash
python3 scripts/training_dataset_builder.py \
  --incidents data/training/positive_incidents.seed.json \
  --split-policy config/training_split_policy.json \
  --graph-input data/replay/graph-inference.v1 \
  --label-candidates data/training/replay_label_candidates.seed.json \
  --out-dir data/training \
  --report ops/reports/training-dataset-builder.latest.json
```

## Important Limitation

This builder creates dataset manifests, not a training-ready GraphSAGE dataset. Candidate transaction hashes still need trace replay and analyst promotion; current provider-only graphs go to the unlabeled pool because they have `trace_unsupported`.

## Check

```bash
python3 scripts/training_dataset_check.py \
  --incidents data/training/positive_incidents.seed.json \
  --snapshot data/training/label_snapshot.v1.json \
  --splits-dir data/training/splits \
  --unlabeled data/training/unlabeled_pool.provider_only.v1.json \
  --label-candidates data/training/replay_label_candidates.seed.json \
  --out ops/reports/training-dataset-check.latest.json
```
