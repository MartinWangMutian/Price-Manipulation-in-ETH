# Label Promotion Runbook

## Purpose

Track analyst decisions for candidate exploit and normal transactions after
historical trace replay. The seed file starts every candidate as pending and
prevents premature training-label promotion.

## Build Template

```bash
python3 scripts/label_promotion_template_builder.py \
  --exploit-queue data/training/trace_replay_queue.v1.json \
  --normal-queue data/training/normal_trace_replay_queue.v1.json \
  --out data/training/label_promotion_decisions.seed.json \
  --report ops/reports/label-promotion-template-builder.latest.json
```

## Audit

```bash
python3 scripts/label_promotion_audit.py \
  --decisions data/training/label_promotion_decisions.seed.json \
  --exploit-queue data/training/trace_replay_queue.v1.json \
  --normal-queue data/training/normal_trace_replay_queue.v1.json \
  --out ops/reports/label-promotion-audit.latest.json
```

Only set a decision to `promoted` after trace replay, rich graph generation, and
analyst confirmation.
