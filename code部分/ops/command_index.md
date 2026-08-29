# Command Index

This index groups the local replay and audit commands by stage.

## Required Inputs

```bash
python3 scripts/ops_contacts_bootstrap.py \
  --report ops/reports/ops-contacts-bootstrap.latest.json
```

```bash
python3 scripts/ops_contacts_bootstrap_selftest.py
```

```bash
python3 scripts/required_inputs_check.py \
  --contacts "${OPS_CONTACTS_CONFIG:-config/ops_contacts.local.json}" \
  --out ops/reports/required-inputs-check.latest.json
```

```bash
python3 scripts/required_inputs_check_selftest.py
```

```bash
python3 scripts/env_local_audit.py \
  --env-file .env.local \
  --out ops/reports/env-local-audit.latest.json
```

```bash
python3 scripts/env_local_audit_selftest.py
```

```bash
python3 scripts/report_secret_audit.py \
  --input ops/reports \
  --out ops/reports/report-secret-audit.latest.json
```

```bash
python3 scripts/report_secret_audit_selftest.py
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

```bash
python3 scripts/provider_trace_capability_probe.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/provider-trace-capability-probe.latest.json
```

```bash
python3 scripts/provider_trace_capability_probe_selftest.py
```

```bash
python3 scripts/main_trace_endpoint_preflight.py \
  --env-file .env.local \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

```bash
python3 scripts/main_trace_endpoint_preflight_selftest.py
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
python3 scripts/context_window_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --address-out data/context/address-context.v1.json \
  --protocol-out data/context/protocol-context.v1.json \
  --report ops/reports/context-window-builder.latest.json
```

```bash
python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1 \
  --protocol-features data/replay/protocol-features.v1 \
  --address-context data/context/address-context.v1.json \
  --protocol-context data/context/protocol-context.v1.json \
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

Strict gate for the frozen paid rich-trace partition:

```bash
python3 scripts/rich_graph_quality_audit.py \
  --trace-input data/replay/trace-bundle.v1/dt=2026-08-29 \
  --parsed-input data/replay/parsed-trace.v1/dt=2026-08-29 \
  --protocol-input data/replay/protocol-features.v1/dt=2026-08-29 \
  --graph-input data/replay/graph-inference.v1/dt=2026-08-29 \
  --out ops/reports/rich-graph-quality-audit.latest.json
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
python3 scripts/replay_label_candidates_check.py \
  --candidates data/training/replay_label_candidates.seed.json \
  --incidents data/training/positive_incidents.seed.json \
  --normal-candidates data/training/normal_replay_candidates.seed.json \
  --out ops/reports/replay-label-candidates-check.latest.json
```

```bash
python3 scripts/trace_replay_queue_builder.py \
  --candidates data/training/replay_label_candidates.seed.json \
  --out data/training/trace_replay_queue.v1.json \
  --report ops/reports/trace-replay-queue-builder.latest.json
```

```bash
python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --dry-run \
  --out ops/reports/historical-trace-replay.latest.json
```

```bash
source .env.local
python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
```

```bash
python3 scripts/historical_trace_replay_selftest.py
python3 scripts/trace_endpoint_preflight_selftest.py
```

```bash
python3 scripts/normal_replay_candidates_builder.py \
  --pending-input data/replay/pending-tx.v1 \
  --positive-candidates data/training/replay_label_candidates.seed.json \
  --target-count 50 \
  --out data/training/normal_replay_candidates.seed.json \
  --queue-out data/training/normal_trace_replay_queue.v1.json \
  --report ops/reports/normal-replay-candidates-builder.latest.json
```

```bash
python3 scripts/normal_replay_candidates_check.py \
  --candidates data/training/normal_replay_candidates.seed.json \
  --queue data/training/normal_trace_replay_queue.v1.json \
  --positive-candidates data/training/replay_label_candidates.seed.json \
  --min-count 50 \
  --out ops/reports/normal-replay-candidates-check.latest.json
```

```bash
python3 scripts/label_readiness_audit.py \
  --out ops/reports/label-readiness-audit.latest.json
```

```bash
python3 scripts/historical_trace_results_audit.py \
  --exploit-report ops/reports/historical-trace-replay.latest.json \
  --normal-report ops/reports/normal-historical-trace-replay.latest.json \
  --preflight-report ops/reports/trace-endpoint-preflight.latest.json \
  --out ops/reports/historical-trace-results-audit.latest.json
```

```bash
python3 scripts/label_promotion_template_builder.py \
  --exploit-queue data/training/trace_replay_queue.v1.json \
  --normal-queue data/training/normal_trace_replay_queue.v1.json \
  --out data/training/label_promotion_decisions.seed.json \
  --report ops/reports/label-promotion-template-builder.latest.json
```

```bash
python3 scripts/label_promotion_audit.py \
  --decisions data/training/label_promotion_decisions.seed.json \
  --exploit-queue data/training/trace_replay_queue.v1.json \
  --normal-queue data/training/normal_trace_replay_queue.v1.json \
  --out ops/reports/label-promotion-audit.latest.json
```

```bash
python3 scripts/training_dataset_builder.py \
  --incidents data/training/positive_incidents.seed.json \
  --split-policy config/training_split_policy.json \
  --graph-input data/replay/graph-inference.v1 \
  --label-candidates data/training/replay_label_candidates.seed.json \
  --out-dir data/training \
  --report ops/reports/training-dataset-builder.latest.json
```

```bash
python3 scripts/training_dataset_check.py \
  --incidents data/training/positive_incidents.seed.json \
  --snapshot data/training/label_snapshot.v1.json \
  --splits-dir data/training/splits \
  --unlabeled data/training/unlabeled_pool.provider_only.v1.json \
  --label-candidates data/training/replay_label_candidates.seed.json \
  --out ops/reports/training-dataset-check.latest.json
```

```bash
python3 scripts/graph_label_exporter.py \
  --decisions data/training/label_promotion_decisions.seed.json \
  --graphs data/replay/graph-inference.v1 \
  --out data/training/graph_labels.v1.json \
  --report ops/reports/graph-label-exporter.latest.json
```

```bash
python3 scripts/graphsage_train.py \
  --graphs data/replay/graph-inference.v1 \
  --labels data/training/graph_labels.v1.json \
  --out-dir models/graphsage/latest \
  --report ops/reports/graphsage-train.latest.json \
  --dry-run
```

```bash
python3 scripts/graphsage_inference_service.py \
  --input data/replay/graph-inference.v1 \
  --model-dir models/graphsage/latest \
  --out ops/reports/graphsage-inference.latest.json
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
source .env.local
python3 scripts/trace_endpoint_preflight.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/trace-endpoint-preflight.latest.json
python3 scripts/historical_trace_replay.py \
  --queue data/training/trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/historical-trace-replay.latest.json
python3 scripts/historical_trace_replay.py \
  --queue data/training/normal_trace_replay_queue.v1.json \
  --method auto \
  --out ops/reports/normal-historical-trace-replay.latest.json
```

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

```bash
python3 scripts/phase_b_completion_audit.py \
  --out ops/reports/phase-b-completion-audit.latest.json
```

```bash
python3 scripts/phase_b_next_action.py \
  --out ops/reports/phase-b-next-action.latest.json
```

```bash
python3 scripts/phase_b_next_action_selftest.py
```

```bash
python3 scripts/phase_b_completion_audit_selftest.py
```

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

```bash
python3 scripts/phase_b_refresh_selftest.py
```

```bash
python3 scripts/artifact_manifest.py \
  --out ops/reports/artifact-manifest.latest.json
```

```bash
python3 scripts/artifact_manifest_selftest.py
```

```bash
python3 scripts/status_summary.py \
  --out ops/status_summary.md
```

## Basic Code Checks

```bash
python3 scripts/validate_schemas.py
python3 -m compileall scripts
```
