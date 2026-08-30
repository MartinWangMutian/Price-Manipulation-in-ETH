# Full Training Stage 5 Runbook

## Scope

Stage 5 locks an isolated PyTorch/PyG environment and proves the minimum
GraphSAGE optimization path. It does not upgrade the production trainer, tune
hyperparameters, evaluate validation data, or read held-out graph files.

## Create the isolated environment

From `code部分/`:

```bash
python3 -m venv .venv-graphsage
.venv-graphsage/bin/python -m pip install \
  -r requirements/graphsage-stage5.lock.txt
.venv-graphsage/bin/python -m pip check
```

The virtual environment is ignored by Git. The lock targets CPython 3.13 on
macOS arm64 and fixes all resolved versions, including PyTorch and PyTorch
Geometric.

## Audit dependencies and device behavior

```bash
.venv-graphsage/bin/python scripts/training_environment_audit.py
```

`--device auto` selects CUDA, then MPS, then CPU. The audit runs a real
`SAGEConv` operation and verifies that the selected device preserves input and
output shape and dtype contracts.

## Recheck the frozen split

```bash
python3 scripts/split_manifest_audit.py
```

Do not continue if this audit fails. Stage 5 reads graph content only from the
`train` split. It may inspect split counts and hashes in the frozen manifest,
but it must load zero validation or held-out graph files and generate zero
held-out predictions.

## Run the minimum training closure

```bash
.venv-graphsage/bin/python scripts/training_smoke_test.py
```

The gate performs:

1. One real training graph through tensorization, forward, BCE loss, backward,
   gradient clipping, optimizer step, checkpoint save, restore, and exact
   resumed-step comparison.
2. One positive and one negative training graph through a 100-step overfit
   check with deterministic algorithms enabled.
3. Model, optimizer, scheduler placeholder, and CPU/device RNG state
   checkpointing.

Checkpoints are written under `models/graphsage/runs/` and remain local. The
committed report stores only relative paths and SHA-256 hashes.

## Reproducibility check

```bash
.venv-graphsage/bin/python scripts/training_smoke_test.py \
  --out-dir models/graphsage/runs/stage5-smoke-repeat \
  --report /tmp/training-smoke.stage5.repeat.json

.venv-graphsage/bin/python scripts/training_smoke_reproducibility_audit.py \
  --second /tmp/training-smoke.stage5.repeat.json
```

The comparison ignores timestamps and output directory names. Data hashes,
seed, device, model/optimizer configuration, loss curve, predictions, gradient
statistics, parameter deltas, restore checks, and checkpoint hashes must match.

## Acceptance gates

- All locked dependencies match and `pip check` reports no broken packages.
- A real `SAGEConv` forward pass is finite on the auto-selected device.
- Single-graph gradients are finite, loss decreases, and parameters update.
- One-batch final loss is at most `0.1` and at most 25% of initial loss.
- The one-positive/one-negative batch reaches 100% training accuracy.
- Checkpoint prediction and resumed-step parameter differences are at most
  `1e-6`.
- The repeat run has identical stable fields.
- Validation and held-out graph files loaded: zero.
- Held-out predictions generated: zero.

Passing these gates authorizes Stage 6 trainer work. It is not a model-quality
claim and does not authorize held-out evaluation.
