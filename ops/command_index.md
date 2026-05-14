# Command Index

This index groups the local replay and audit commands by stage.

## Required Inputs

```bash
python3 scripts/required_inputs_check.py \
  --contacts "${OPS_CONTACTS_CONFIG:-config/ops_contacts.example.json}" \
  --out ops/reports/required-inputs-check.latest.json
```

## Provider and Node Checks

```bash
source .env.local
python3 scripts/node_health_check.py \
  --config config/rpc_endpoints.example.json \
  --out ops/reports/node-health.latest.json
```

```bash
source .env.local
python3 scripts/provider_smoke_test.py \
  --out ops/reports/provider-smoke.latest.json
```

## Pending and Trace Replay

```bash
python3 scripts/pending_replay_check.py \
  --input data/replay/pending-tx.v1 \
  --out ops/reports/pending-replay-check-p2a.latest.json
```

```bash
python3 scripts/pending_trace_worker.py \
  --input data/replay/pending-tx.v1 \
  --out ops/reports/pending-trace-worker.latest.json
```

```bash
python3 scripts/trace_replay_check.py \
  --input data/replay/trace-bundle.v1 \
  --allow-replay-duplicates \
  --out ops/reports/trace-replay-check-p2b-deduped.latest.json
```

```bash
python3 scripts/trace_bundle_audit.py \
  --input data/replay/trace-bundle.v1 \
  --out ops/reports/trace-bundle-audit.latest.json
```

## Parse, Role, and Graph

```bash
python3 scripts/trace_parser.py \
  --input data/replay/trace-bundle.v1 \
  --write-replay \
  --out ops/reports/trace-parser.latest.json
```

```bash
python3 scripts/protocol_role_enricher.py \
  --input data/replay/parsed-trace.v1 \
  --write-replay \
  --out ops/reports/protocol-role-enricher.latest.json
```

```bash
python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --write-replay \
  --write-snapshot \
  --out ops/reports/cash-flow-graph-builder.latest.json
```

```bash
python3 scripts/graph_replay_check.py \
  --input data/replay/graph-inference.v1 \
  --out ops/reports/graph-replay-check.latest.json
```

```bash
python3 scripts/graph_quality_check.py \
  --input data/replay/graph-inference.v1 \
  --builder-report ops/reports/cash-flow-graph-builder.latest.json \
  --out ops/reports/graph-quality-check.latest.json
```

## Risk, Alert, and RAG

```bash
python3 scripts/rule_baseline_scorer.py \
  --input data/replay/graph-inference.v1 \
  --write-replay \
  --write-hit-samples \
  --out ops/reports/rule-baseline-scorer.latest.json
```

```bash
python3 scripts/risk_replay_check.py \
  --input data/replay/risk-score.v1 \
  --out ops/reports/risk-replay-check.latest.json
```

```bash
python3 scripts/alert_orchestrator.py \
  --risk-input data/replay/risk-score.v1 \
  --graph-input data/replay/graph-inference.v1 \
  --trace-input data/replay/trace-bundle.v1 \
  --write-replay \
  --out ops/reports/alert-orchestrator.latest.json \
  --audit-log ops/audit/alert-orchestrator.jsonl
```

```bash
python3 scripts/alert_replay_check.py \
  --input data/replay/alert-event.v1 \
  --audit-log ops/audit/alert-orchestrator.jsonl \
  --out ops/reports/alert-replay-check.latest.json
```

```bash
python3 scripts/rag_index_builder.py \
  --documents data/rag/documents.seed.json \
  --out data/rag/index/knowledge-snapshot.seed-2026-05-14.json \
  --report ops/reports/rag-index-builder.latest.json
```

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

```bash
python3 scripts/rag_explanation_check.py \
  --input data/replay/rag-explanation.v1 \
  --alerts data/replay/alert-event.v1 \
  --audit-log ops/audit/rag-explanation-builder.jsonl \
  --out ops/reports/rag-explanation-check.latest.json
```

## Console and Evaluation

```bash
python3 scripts/analyst_console_view_builder.py \
  --alerts data/replay/alert-event.v1 \
  --risks data/replay/risk-score.v1 \
  --graphs data/replay/graph-inference.v1 \
  --traces data/replay/trace-bundle.v1 \
  --rag data/replay/rag-explanation.v1 \
  --out-dir data/console \
  --audit-trail data/console/review-audit-trail.v1.jsonl \
  --report ops/reports/analyst-console-view-builder.latest.json
```

```bash
python3 scripts/analyst_console_view_check.py \
  --console-dir data/console \
  --state-machine config/review_state_machine.json \
  --out ops/reports/analyst-console-view-check.latest.json
```

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

## Readiness and Audits

```bash
python3 scripts/load_test_replay.py \
  --pending data/replay/pending-tx.v1 \
  --parsed data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --graphs data/replay/graph-inference.v1 \
  --risks data/replay/risk-score.v1 \
  --alerts data/replay/alert-event.v1 \
  --traces data/replay/trace-bundle.v1 \
  --out ops/reports/load-test-replay.latest.json
```

```bash
python3 scripts/failure_drill.py \
  --node-health ops/reports/node-health.latest.json \
  --trace-report ops/reports/pending-trace-worker.latest.json \
  --rag-timeout-report ops/reports/rag-explanation-builder-timeout.latest.json \
  --alert-replay-check ops/reports/alert-replay-check.latest.json \
  --graphs data/replay/graph-inference.v1 \
  --risks data/replay/risk-score.v1 \
  --alerts data/replay/alert-event.v1 \
  --out ops/reports/failure-drill.latest.json \
  --runbook ops/incident_runbook.generated.md
```

```bash
python3 scripts/gray_launch_readiness.py \
  --config config/gray_launch.json \
  --out ops/reports/gray-launch-readiness.latest.json
```

```bash
python3 scripts/go_no_go_audit.py \
  --out ops/reports/go-no-go-audit.latest.json
```

```bash
python3 scripts/validation_metrics_audit.py \
  --out ops/reports/validation-metrics-audit.latest.json
```

```bash
python3 scripts/project_status_audit.py \
  --out ops/reports/project-status.latest.json \
  --blockers ops/blocker_register.md
```

## Basic Code Checks

```bash
python3 scripts/validate_schemas.py
python3 -m compileall scripts
```
