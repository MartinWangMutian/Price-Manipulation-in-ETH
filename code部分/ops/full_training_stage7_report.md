# Full Training Stage 7 Report

## Outcome

Stage 7 is complete. GraphSAGE, a pooled-feature MLP, and the deterministic rule
baseline were run on the same frozen engineering-smoke split with aligned
metrics and predictions. Best-checkpoint restoration, early stopping,
single-graph inference consistency, output hashes, and held-out isolation all
passed.

The implementation commit used by both trained runs is
`49665eb544ec523a8ab7b73f43d6f98070692c82`.

This result validates the experiment plumbing. It does not establish model
quality or GraphSAGE superiority.

## Sample accounting

- Candidate rich graphs: 57
- Promoted labels: 55 (5 positive, 50 negative)
- Evidence-insufficient graphs retained as unlabeled: 2
- Train graphs opened: 33 (3 positive, 30 negative)
- Validation graphs opened: 11 (1 positive, 10 negative)
- Held-out manifest items: 11 (1 positive, 10 negative)
- Held-out graph files opened/evaluated/predicted: 0/0/0

The experiment does not force the two unlabeled event-related transactions into
the positive class and does not use frozen test records to select a model.

## Same-split comparison

Validation metrics at the fixed threshold of 0.5:

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 | Brier |
|---|---:|---:|---:|---:|---:|---:|
| GraphSAGE | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2347 |
| Pooled-feature MLP | 1.0000 | 1.0000 | 0.0909 | 1.0000 | 0.1667 | 0.2862 |
| Rule baseline | 0.0909 | 0.5000 | 0.0000 | 0.0000 | 0.0000 | 0.0909 |

PR-AUC uses tie-aware step-wise average precision. A constant-score classifier
therefore receives the positive prevalence (`1/11 = 0.0909`) instead of the
inflated value produced by trapezoidal interpolation across a single large tie.

GraphSAGE and the pooled MLP both ranked the one validation positive above all
ten negatives. Their threshold behavior was not useful: GraphSAGE predicted
every validation item negative, while the pooled MLP predicted every item
positive. Because the validation set has only one positive event, the perfect
ranking metrics have extremely high uncertainty. The experiment provides no
evidence that GraphSAGE adds value over pooled features.

## Training behavior

GraphSAGE:

- Hidden dimension/layers: 64/2
- Best epoch: 4
- Last epoch: 19
- Early stopped: yes, after 15 stale epochs
- Train PR-AUC/ROC-AUC: 0.8056/0.9778
- Train precision/recall/F1 at 0.5: 1.0000/0.3333/0.5000
- Best checkpoint SHA-256:
  `e6788bfbee1a2cb2129bcbfb6de2d8e16e021fa510b5fde6298cb5dc88c564b0`
- Last checkpoint SHA-256:
  `c21018be0e598f8b2997f98f9486ed765256777d838adf81d022b9b2be2ea07a`
- Run manifest SHA-256:
  `238a8c5697187f8a951e43867b754606225c393a3d278c0332e74b52d7d92b37`

Pooled-feature MLP:

- Hidden dimension: 64
- Best epoch: 1
- Last epoch: 16
- Early stopped: yes, after 15 stale epochs
- Train PR-AUC/ROC-AUC: 1.0000/1.0000
- Train precision/recall/F1 at 0.5: 0.0909/1.0000/0.1667
- Best checkpoint SHA-256:
  `655be109ea896a8166ec723f6258670d19e599af5392ef000071a277325db28a`
- Last checkpoint SHA-256:
  `aa47ebec4dbd7093bafa3baad38b468a94a731ccd66182ac6ab62a90cf0f9cba`
- Run manifest SHA-256:
  `f3972361ce4511791fe38ef27629994820e4b0ace02124f081b62aa64d2b84b5`

Both neural baselines used seed `20260830`, class-balanced focal loss, AdamW,
cosine learning-rate decay, gradient clipping at 1.0, and validation PR-AUC
early stopping.

## Inference consistency

The selected GraphSAGE checkpoint scored all 44 allowed graphs in three ways:
split batch, one graph at a time, and comparison with the stored prediction.

- Graphs checked: 44
- Maximum batch/single difference: `5.960464477539063e-08`
- Maximum single/stored difference: `5.962525634339855e-08`
- Required tolerance: `1e-6`
- Status: passed

## Artifact and isolation audit

- Three-model aligned predictions: 44 unique transactions
- Prediction splits: train and validation only
- GraphSAGE fixed artifact hashes: passed
- Pooled MLP model/metrics/prediction/curve hashes: passed
- Pooled MLP best/last checkpoint contracts: passed
- Graph/data/label/split hashes: matched
- Held-out graph files loaded or predictions emitted: zero
- Audit errors: zero

Binary checkpoints, predictions, curves, and run manifests remain in the
Git-ignored local run directories. Committed evidence contains only controlled
reports, configuration, references, and hashes.

## Verification

- All repository `*_selftest.py` scripts passed.
- Training dependency lock has no broken requirements.
- Seven schemas and 919 records validated.
- Inference consistency and Stage 7 artifact audits passed.
- Report secret scan found no provider token paths.
- Git whitespace checks passed.

## Canonical evidence

- `config/engineering_smoke.stage7.v1.json`
- `ops/reports/graphsage-train.stage7.latest.json`
- `ops/reports/engineering-smoke.stage7.latest.json`
- `ops/reports/graphsage-inference-consistency.stage7.latest.json`
- `ops/reports/engineering-smoke-audit.stage7.latest.json`
- `ops/full_training_stage7_runbook.md`

## Next gate

Stage 8 must expand the research dataset before any formal conclusion or frozen
test evaluation. The minimum target remains at least 20 independent attack
events, 100 positive rich graphs, and 1,000 matched negative rich graphs,
including hard negatives. Threshold calibration and five-seed experiments wait
until that dataset exists.
