# Phase 1 Replay Storage and Artifact Layout

**Version:** `replay-storage.v1`

Replay storage must make any alert reproducible from the exact event, trace,
graph, model, and evidence versions used when it was emitted.

## Directory Layout

```text
data/
  replay/
    pending-tx.v1/dt=YYYY-MM-DD/hour=HH/
    trace-bundle.v1/dt=YYYY-MM-DD/hour=HH/
    graph-inference.v1/dt=YYYY-MM-DD/hour=HH/
    risk-score.v1/dt=YYYY-MM-DD/hour=HH/
    alert-event.v1/dt=YYYY-MM-DD/hour=HH/
    rag-explanation.v1/dt=YYYY-MM-DD/hour=HH/
  raw-trace/
    chain_id=1/dt=YYYY-MM-DD/hour=HH/
  graph-snapshot/
    chain_id=1/dt=YYYY-MM-DD/hour=HH/
  model-input/
    model_version=<version>/dt=YYYY-MM-DD/
  model-output/
    model_version=<version>/dt=YYYY-MM-DD/
  alert-version/
    alert_version=<version>/dt=YYYY-MM-DD/
```

## Naming Rules

| Artifact | File name |
|---|---|
| Event replay record | `<event_id>.json` |
| Raw trace | `<chain_id>-<tx_hash>-<trace_source>.json` |
| Standardized trace | `<chain_id>-<tx_hash>-trace-bundle.v1.json` |
| Graph snapshot | `<graph_id>.json` |
| Model input | `<chain_id>-<tx_hash>-<feature_ver>.json` |
| Model output | `<chain_id>-<tx_hash>-<model_version>.json` |
| Alert version | `<alert_id>-<alert_version>.json` |

## Required Replay Fields

Every replayable artifact must preserve:

- `event_id`
- `schema_ver`
- `chain_id`
- `created_at`
- `idempotency_key`
- upstream event references
- source endpoint name
- model, feature, threshold, or knowledge snapshot version where applicable

## Retention Rule

Phase 1 retains all replay artifacts until the first go/no-go review. A
production retention policy must be approved before gray launch.

