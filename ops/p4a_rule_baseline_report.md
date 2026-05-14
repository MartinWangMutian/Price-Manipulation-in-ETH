# P4-A Rule Baseline Report

## Scope

Implemented deterministic rule-baseline scoring as the model-unavailable fallback path.

## Implemented Rules

- Abnormal profit path
- Oracle read/write same transaction
- Excessive slippage
- Thin liquidity trade
- Flash-loan path

## Outputs

- `risk-score.v1` replay events
- rule score
- severity
- reason codes
- model fallback metadata through `model_reject_reason=model_unavailable_rule_fallback`
- rule hit sample persistence for non-fallback rule hits

## Current Validation

Synthetic self-test covers abnormal profit path, oracle/protocol same-transaction touch, flash-loan path, score aggregation, severity mapping, and fallback metadata.

Provider-only graph replay generated 110 `risk-score.v1` records and the independent risk replay check passed.

Current provider-only result:

- `scores_generated`: 110
- `severity_counts`: `low=110`
- `reason_counts`: `FEATURE_TRACE_UNSUPPORTED=110`, `RULE_BASELINE_NO_RICH_EVIDENCE=110`
- `model_reject_reason`: `model_unavailable_rule_fallback`
- duplicate idempotency keys: empty
- errors: empty

Low fallback scores are expected because the current graphs contain no rich call/transfer evidence.

## Remaining Runtime Gap

Meaningful rule hits require real transfer/call/protocol graph edges from Geth or Erigon traces. Provider-only fallback confirms pipeline continuity but not detection quality.
