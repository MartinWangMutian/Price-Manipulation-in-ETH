# Full Training Stage 7 Runbook

## Scope

Stage 7 runs the first end-to-end engineering smoke comparison for the rule
baseline, pooled-feature MLP, and GraphSAGE. All three models use the same
frozen Stage 4 labels, splits, threshold, and metric implementation.

The source snapshot contains 57 candidate graphs. Analyst promotion retained
55 labeled graphs (5 positive, 50 negative) and left two evidence-insufficient
event-related graphs unlabeled. Stage 7 does not override those analyst
decisions. Optimization and validation open 33 train and 11 validation graphs;
the 11 held-out graph files remain unopened.

This is an engineering smoke experiment, not a research-quality result.

## Preconditions

From `code部分/`:

```bash
.venv-graphsage/bin/python -m pip check
python3 scripts/split_manifest_audit.py
python3 scripts/graphsage_train_selftest.py
python3 scripts/engineering_smoke_baselines_selftest.py
python3 scripts/graphsage_inference_consistency_selftest.py
```

The configuration is frozen in
`config/engineering_smoke.stage7.v1.json`. Model selection uses the tie-aware,
step-wise average-precision definition of PR-AUC. A constant-score classifier
therefore receives the positive prevalence rather than an inflated
trapezoidal interpolation score.

## Run GraphSAGE

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
  --focal-gamma 2.0 \
  --gradient-clip 1.0 \
  --threshold 0.5 \
  --run-id stage7-graphsage-engineering-smoke \
  --report ops/reports/graphsage-train.stage7.latest.json
```

The trainer writes the fixed Stage 6 artifact set and restores the checkpoint
with the best validation PR-AUC before generating predictions.

## Train the pooled MLP and compare baselines

```bash
.venv-graphsage/bin/python scripts/engineering_smoke_baselines.py \
  --config config/engineering_smoke.stage7.v1.json \
  --graphsage-run-dir models/graphsage/runs/stage7-graphsage-engineering-smoke \
  --run-id stage7-baselines-engineering-smoke \
  --report ops/reports/engineering-smoke.stage7.latest.json
```

The pooled-feature MLP uses mean and maximum pooling over the same address and
protocol node feature vectors, plus node count, edge count, address ratio, and
protocol ratio. It receives semantic incident-edge summaries already present
in node features but performs no graph message passing. This makes it a useful
control for whether adjacency-aware GraphSAGE adds value.

The rule baseline is deterministic and uses `config/rule_baseline.json` without
label fitting. The comparison output includes train and validation metrics and
44 aligned per-transaction predictions for all three methods.

## Audit batch and single-graph inference

```bash
.venv-graphsage/bin/python scripts/graphsage_inference_consistency_audit.py \
  --run-dir models/graphsage/runs/stage7-graphsage-engineering-smoke \
  --split-manifest data/training/split_manifest.stage4.v1.json \
  --device auto \
  --tolerance 0.000001 \
  --out ops/reports/graphsage-inference-consistency.stage7.latest.json
```

The auditor scores every allowed graph both in its split batch and alone, then
compares both values with the stored best-checkpoint prediction. Maximum
absolute differences must remain at or below `1e-6`.

Finally audit both run packages:

```bash
.venv-graphsage/bin/python scripts/engineering_smoke_artifact_audit.py \
  --baseline-run-dir models/graphsage/runs/stage7-baselines-engineering-smoke \
  --graphsage-run-dir models/graphsage/runs/stage7-graphsage-engineering-smoke \
  --split-manifest data/training/split_manifest.stage4.v1.json \
  --consistency-report ops/reports/graphsage-inference-consistency.stage7.latest.json \
  --out ops/reports/engineering-smoke-audit.stage7.latest.json
```

## Acceptance gates

- GraphSAGE and pooled MLP complete forward, backward, early stopping, best
  checkpoint restoration, metrics, predictions, curves, and manifests.
- Rule, MLP, and GraphSAGE metrics use exactly the same 33/11 train/validation
  records and threshold.
- Comparison predictions contain exactly 44 unique transactions and no
  held-out split.
- GraphSAGE batch, single-graph, and stored predictions agree within `1e-6`.
- Every report identifies the run as `engineering_smoke_only`.
- Held-out graph files loaded, evaluated, or predicted: zero.
- Any high metric is reported with the one-positive validation limitation and
  is not presented as a research result.

Passing Stage 7 authorizes research-scale data expansion in Stage 8. It does
not authorize frozen test evaluation.
