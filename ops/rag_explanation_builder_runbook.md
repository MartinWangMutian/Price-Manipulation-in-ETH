# RAG Explanation Builder Runbook

## Purpose

Build `rag-explanation.v1` records after alerts have already been emitted. The builder constrains factual sentences to evidence refs and preserves alert score, severity, and reason codes.

## Replay Command

```bash
python3 scripts/rag_explanation_builder.py \
  --alerts data/replay/alert-event.v1 \
  --graphs data/replay/graph-inference.v1 \
  --rag-index data/rag/index/knowledge-snapshot.seed-2026-05-14.json \
  --templates config/rag_explanation_templates.json \
  --include-low \
  --write-replay \
  --audit-log ops/audit/rag-explanation-builder.jsonl \
  --out ops/reports/rag-explanation-builder.latest.json
```

## Timeout Drill

```bash
python3 scripts/rag_explanation_builder.py \
  --alerts data/replay/alert-event.v1 \
  --graphs data/replay/graph-inference.v1 \
  --rag-index data/rag/index/knowledge-snapshot.seed-2026-05-14.json \
  --templates config/rag_explanation_templates.json \
  --include-low \
  --simulate-timeout \
  --out ops/reports/rag-explanation-builder-timeout.latest.json
```

## Replay Check

```bash
python3 scripts/rag_explanation_check.py \
  --input data/replay/rag-explanation.v1 \
  --alerts data/replay/alert-event.v1 \
  --audit-log ops/audit/rag-explanation-builder.jsonl \
  --out ops/reports/rag-explanation-check.latest.json
```
