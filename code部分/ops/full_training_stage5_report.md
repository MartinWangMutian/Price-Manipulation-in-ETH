# Full Training Stage 5 Report

## Outcome

Stage 5 is complete. The project now has a locked, isolated GraphSAGE training
environment and a deterministic minimum training closure using only two graphs
from the frozen `train` split.

This is an engineering gate, not a validation result or model-quality claim.

## Environment

- Python: 3.13.2
- PyTorch: 2.13.0
- PyTorch Geometric: 2.8.0.post1
- Fully locked packages: 29
- Platform: macOS arm64
- Requested device: `auto`
- Selected device: CPU
- CUDA available: no
- MPS built into PyTorch: yes
- MPS available to this runtime: no
- `pip check`: no broken requirements
- SAGEConv output shape/dtype contract: consistent and finite

The virtual environment is `.venv-graphsage` and is ignored by Git. The lock
file hash is recorded in the environment audit.

## Data isolation

- Frozen split manifest verified: yes
- Graph files loaded from train: 2
- Validation graph files loaded: 0
- Held-out test graph files loaded: 0
- Held-out test predictions: 0
- Feature version: `cash-flow-graph-builder.v1`
- Label version: `engineering-smoke-labels.stage4.v1`

## Single-graph gate

- Graph: one positive training graph
- Nodes: 36
- Graph edges: 171
- Input feature dimension: 31
- Loss before one update: 0.6432282925
- Loss after one update: 0.4085523188
- Gradients finite: yes
- Gradient norm before clipping: 0.6156158447
- Parameter L1 delta: 54.4495264590
- Restored prediction max difference: 0.0
- Continued-step loss difference after restore: 0.0
- Continued-step parameter max difference after restore: 0.0

## One-batch overfit gate

- Batch: one positive and one negative training graph
- Steps: 100
- Initial loss: 0.6983598471
- Final loss: approximately `1.21817e-26`
- Final/initial loss ratio: approximately `1.74433e-26`
- Training accuracy: 100%
- Gradients finite: yes
- Maximum observed gradient norm: 0.5374900699
- Parameter L1 delta: 625.2753400207
- Restored prediction max difference: 0.0
- Continued-step loss difference after restore: 0.0
- Continued-step parameter max difference after restore: 0.0

The near-zero final gradient is expected after deliberately saturating a
two-sample overfit check. It must not be interpreted as evidence that the full
dataset is converged.

## Reproducibility

The smoke run was repeated with the same seed and CPU device. Data hashes,
configuration, selected graphs, loss curve, predictions, gradient statistics,
parameter deltas, restore checks, and checkpoint hashes were identical.

- Seed: 20260830
- Single-graph checkpoint SHA-256:
  `f79de72d8bfa0bef2da5bcc914aa9d1d145a8ba9df59e95d9f636cc58f26f0c2`
- One-batch checkpoint SHA-256:
  `17e9ad0c1bd1ad0c473bedea5b4866babb8b8086a7c8d665f80fa58f96f5e5fd`

The checkpoint binaries remain under ignored `models/graphsage/runs/` paths;
the repository commits only hashes and relative references.

## Canonical artifacts

- `requirements/graphsage-stage5.in`
- `requirements/graphsage-stage5.lock.txt`
- `config/training_smoke.stage5.v1.json`
- `ops/reports/training-environment.stage5.latest.json`
- `ops/reports/training-smoke.stage5.latest.json`
- `ops/reports/training-smoke-reproducibility.stage5.latest.json`
- `ops/full_training_stage5_runbook.md`

## Next gate

Stage 6 may now upgrade the legacy trainer to consume the frozen split manifest,
support configurable architecture and optimization settings, checkpoint resume,
validation PR-AUC early stopping, and complete run manifests. Held-out test
evaluation remains prohibited.
