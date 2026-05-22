# Offline Evaluation Runbook

## Purpose

Build local P6-B replay and evaluation reports from available replay artifacts.

## Command

```bash
python3 scripts/offline_evaluation.py \
  --alerts data/replay/alert-event.v1 \
  --risks data/replay/risk-score.v1 \
  --graphs data/replay/graph-inference.v1 \
  --traces data/replay/trace-bundle.v1 \
  --rag data/replay/rag-explanation.v1 \
  --incidents data/training/positive_incidents.seed.json \
  --label-snapshot data/training/label_snapshot.v1.json \
  --out-dir data/evaluation \
  --report ops/reports/offline-evaluation.latest.json \
  --threshold-report ops/reports/threshold-calibration.latest.json
```

## Limitations

False positives, false negatives, and lead time are intentionally null until confirmed positive and negative replay sets exist.
