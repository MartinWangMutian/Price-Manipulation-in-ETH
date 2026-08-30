# Full Training Stage 6 Runbook

## Scope

Stage 6 upgrades the GraphSAGE trainer. It consumes the frozen Stage 4 grouped
split, loads only `train` and `validation` graph references, and selects the
best checkpoint with validation PR-AUC. It never opens, predicts, or evaluates
the `held_out_test` graph files.

This stage validates training engineering. The 55 promoted labels are still an
engineering-smoke dataset and cannot support a research-quality generalization
claim.

## Preconditions

From `code部分/`:

```bash
.venv-graphsage/bin/python -m pip check
python3 scripts/split_manifest_audit.py
.venv-graphsage/bin/python scripts/graphsage_model_selftest.py
python3 scripts/graphsage_train_selftest.py
```

Use the locked environment from Stage 5. Stop if the split is not frozen, if a
group appears in multiple splits, if a graph hash or feature version differs,
or if either train or validation lacks one class.

## Validate inputs without optimizing

```bash
.venv-graphsage/bin/python scripts/graphsage_train.py \
  --split-manifest data/training/split_manifest.stage4.v1.json \
  --device auto \
  --run-id stage6-dry-run \
  --dry-run
```

Dry-run validates the manifest and all 44 train/validation graph references,
including their SHA-256 values. It skips all held-out graph references.

## Start a training run

```bash
.venv-graphsage/bin/python scripts/graphsage_train.py \
  --split-manifest data/training/split_manifest.stage4.v1.json \
  --device auto \
  --seed 20260830 \
  --batch-size 8 \
  --hidden-dim 64 \
  --num-layers 2 \
  --dropout 0.1 \
  --lr 0.001 \
  --weight-decay 0.0001 \
  --epochs 100 \
  --patience 15 \
  --monitor pr_auc \
  --loss focal \
  --gradient-clip 1.0 \
  --run-id stage7-engineering-smoke
```

The default class-balanced focal loss can be replaced by `--loss weighted_bce`.
AdamW uses betas `(0.9, 0.95)` and epsilon `1e-10`; a cosine scheduler changes
the learning rate each epoch, and gradients are clipped before every optimizer
step.

## Resume an interrupted run

Use `last_model.pt`, keep all model, optimizer, seed, split, loss, scheduler,
batch, epoch, patience, and threshold arguments identical, and choose either
the original run ID or a new one:

```bash
.venv-graphsage/bin/python scripts/graphsage_train.py \
  --split-manifest data/training/split_manifest.stage4.v1.json \
  --device auto \
  --seed 20260830 \
  --batch-size 8 \
  --hidden-dim 64 \
  --num-layers 2 \
  --dropout 0.1 \
  --lr 0.001 \
  --weight-decay 0.0001 \
  --epochs 100 \
  --patience 15 \
  --monitor pr_auc \
  --loss focal \
  --gradient-clip 1.0 \
  --run-id stage7-engineering-smoke-resumed \
  --resume models/graphsage/runs/stage7-engineering-smoke/last_model.pt
```

Resume is rejected when the model configuration or the data/optimization
contract differs. The paired `best_model.pt` must be present next to the last
checkpoint so best-model provenance is preserved.

## Fixed run artifacts

Every completed run writes under `models/graphsage/runs/<run-id>/`:

- `best_model.pt`: checkpoint selected by validation PR-AUC.
- `last_model.pt`: latest resumable model, optimizer, scheduler, and RNG state.
- `metrics.json`: best-model train/validation metrics and an explicit untouched
  held-out record.
- `predictions.jsonl`: train and validation predictions only.
- `run_manifest.json`: Git commit, split/data/label hashes, feature and label
  versions, model and optimizer configuration, seed, dependencies, device,
  duration, resume provenance, output references, and output hashes.
- `curves.json` and `curves.csv`: loss, learning rate, pre-clipping gradient
  norms, validation PR-AUC, and validation ROC-AUC by epoch.

Model binaries and run outputs remain ignored by Git. Commit only audit reports,
hashes, configuration, and documentation.

## Audit a completed run

```bash
.venv-graphsage/bin/python scripts/graphsage_train_artifact_audit.py \
  --run-dir models/graphsage/runs/stage7-engineering-smoke \
  --split-manifest data/training/split_manifest.stage4.v1.json
```

Add `--require-resume` when auditing a resume exercise. Acceptance requires all
fixed artifacts and hashes to match, checkpoint contracts to match the frozen
split, exactly 44 train/validation predictions, and zero held-out graph loads,
predictions, or evaluations.

Passing Stage 6 authorizes the Stage 7 engineering smoke run. It does not
authorize held-out evaluation; that remains frozen until the model and
threshold are finalized.
