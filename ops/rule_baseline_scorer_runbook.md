# Rule Baseline Scorer Runbook

## Purpose

Phase 4-A deterministic fallback scorer. It converts `graph-inference.v1` replay records into `risk-score.v1` events when the GNN model is unavailable or not yet trained.

## Inputs

- `data/replay/graph-inference.v1/**.json`
- `config/rule_baseline.json`
- `config/reason_codes.json`

## Commands

Run the synthetic rule self-test:

```bash
python3 scripts/rule_baseline_scorer_selftest.py
```

Score current graph replay records:

```bash
python3 scripts/rule_baseline_scorer.py \
  --input data/replay/graph-inference.v1 \
  --write-replay \
  --write-hit-samples \
  --out ops/reports/rule-baseline-scorer.latest.json
```

Validate written risk scores:

```bash
python3 scripts/risk_replay_check.py \
  --input data/replay/risk-score.v1 \
  --out ops/reports/risk-replay-check.latest.json
```

## Provider-only note

Provider-only graphs have no call, transfer, or protocol evidence. The expected fallback score is low with `RULE_BASELINE_NO_RICH_EVIDENCE` and `FEATURE_TRACE_UNSUPPORTED` reasons.
