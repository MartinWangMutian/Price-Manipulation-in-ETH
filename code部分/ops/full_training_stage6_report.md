# Full Training Stage 6 Report

## Outcome

Stage 6 is complete. The legacy all-labeled, single-batch trainer has been
replaced by a configurable mini-batch GraphSAGE trainer that is bound to the
frozen Stage 4 grouped split and selects checkpoints with validation PR-AUC.

The implementation commit used by the acceptance run is
`4955da5681dfa2caded502c952e5e890d1eb3e1d`.

This is a training-system acceptance result, not a model-quality or research
generalization claim.

## Trainer contract

The trainer now supports:

- frozen `--split-manifest` input and strict graph/content hash checks;
- `--device auto`, deterministic seed, mini-batch size, hidden dimension,
  number of GraphSAGE layers, and dropout;
- learning rate, weight decay, epochs, patience, run ID, and resume path;
- class-balanced focal loss or weighted BCE;
- AdamW, cosine learning-rate scheduling, and pre-update gradient clipping;
- validation PR-AUC early stopping and best/last checkpoints;
- model, optimizer, scheduler, RNG, history, and data/optimization contract
  restoration;
- fixed metrics, prediction, run-manifest, and curve artifacts.

`forward_logits` is used for numerically stable training while the existing
probability-returning model interface remains available to inference callers.
One-, two-, and three-layer model topologies passed shape and probability
contract checks.

## Data isolation

Dry-run verified every allowed graph reference and hash:

- Train graph files loaded: 33 (3 positive, 30 negative)
- Validation graph files loaded: 11 (1 positive, 10 negative)
- Held-out manifest items: 11
- Held-out graph files loaded: 0
- Held-out predictions/evaluations: 0
- Feature version: `cash-flow-graph-builder.v1`
- Label version: `engineering-smoke-labels.stage4.v1`
- Split content hash:
  `dbd05212393359c2806e4746d4994f20eece05ac7529e18d93d1cd8e5a757a8b`
- Graph data hash:
  `ab23f5e592c889081e4b004bacd4122b7097bf6880d1b1de375bd342521e18bb`

The loader reads split metadata for all items but opens graph files only after
filtering to train and validation. The artifact audit found exactly 44
predictions and only the `train` and `validation` split names.

## Acceptance and resume exercise

The acceptance run used CPU, seed `20260830`, two GraphSAGE layers, hidden
dimension 16, batch size 8, class-balanced focal loss, AdamW, cosine scheduling,
and gradient clipping at 1.0.

The base run stopped after epoch 2 with patience 1. The resume run restored
`last_model.pt`, started at epoch 3, preserved the epoch-1 best checkpoint, and
completed the requested resume step. The audit found no checkpoint contract or
output hash errors.

- Run ID: `stage6-acceptance-resume-4955da5`
- Run manifest SHA-256:
  `9158641baad216cf78155b6b17c384aa782c306094903c18aef27b273c565c64`
- Best checkpoint SHA-256:
  `f58e8501b6cb4a242cd6437ebaad8c3dfefcfb26fc8b8ac014edab091852f20e`
- Last checkpoint SHA-256:
  `31878d6016e5dfdf9d24ec868197b416e91b4d5ba3837775afecc364e047935e`
- Best epoch: 1
- Last epoch: 3
- Validation PR-AUC at selected checkpoint: 1.0
- Held-out graph files loaded/predicted: 0/0

The validation set contains only one positive event. In addition, the default
0.5 threshold predicted every acceptance sample as negative, so validation
recall and F1 were both zero even though ranking PR-AUC was 1.0. These numbers
are intentionally reported to prevent the tiny acceptance run from being
misread as a useful trained detector. Threshold selection and meaningful model
comparison belong to later stages.

## Fixed artifacts verified

The local, Git-ignored run directory contains and the auditor verified:

- `best_model.pt`
- `last_model.pt`
- `metrics.json`
- `predictions.jsonl`
- `run_manifest.json`
- `curves.json`
- `curves.csv`

The run manifest records the Git commit, split/data/label hashes, feature and
label versions, model and optimization configuration, random seed, dependency
versions, device, duration, resume source, artifact references, and artifact
hashes. Binary checkpoints remain outside Git.

## Verification

- All repository `*_selftest.py` scripts passed.
- Seven schemas and 919 records validated.
- The locked environment has no broken requirements.
- PyTorch 2.13.0 and PyTorch Geometric 2.8.0.post1 were recorded.
- Dry-run, base training, resume training, and artifact audit all returned
  successful status.
- Git diff whitespace checks passed.

## Canonical evidence

- `ops/reports/graphsage-train-dry-run.stage6.latest.json`
- `ops/reports/graphsage-train.stage6.latest.json`
- `ops/reports/graphsage-train-artifact-audit.stage6.latest.json`
- `ops/full_training_stage6_runbook.md`

## Next gate

Stage 7 may run the 55 promoted graph engineering smoke experiment and compare
GraphSAGE with the rule baseline and pooled-feature MLP under the same split.
The held-out test split remains frozen and must not be used in Stage 7 model
selection.
