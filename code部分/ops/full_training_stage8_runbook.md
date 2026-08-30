# Full Training Stage 8 Runbook

## Scope

Stage 8 builds the versioned research-expansion pipeline and runs only its
cost-bounded pilot. It does not complete the research dataset, promote labels,
open the frozen held-out split, or authorize Stage 9 experiments.

The minimum research target remains 20 independent verified attack events,
100 promoted positive rich graphs, and 1,000 promoted matched negative rich
graphs including hard negatives. The event catalog is an evidence index, not a
label file: every graph still requires human review before promotion.

## Safety and external inputs

Run from `code部分/`. The root `../.env.local` contains the provider endpoint.
Map it only in the process environment and never print it:

```bash
set -a
source ../.env.local
set +a
export ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"
export HISTORICAL_TRACE_METHOD="trace_transaction"
```

Only `trace_transaction` is allowed. Keep `--retries 1`, `--fail-fast`, and
`--skip-existing`. The configuration has `stop_after_pilot=true`; do not remove
that gate until the pilot cost is checked in the provider billing dashboard
and the next batch is explicitly authorized.

The negative screen uses two external, temporary inputs:

- a pinned checkout of DeFiHackLabs under `/tmp/defihacklabs-main`;
- the current OFAC SDN CSV under `/tmp/ofac-sdn-stage8.csv`.

Neither raw external input nor raw provider response belongs in Git. Reports
store only source references, versions, sizes, hashes, and aggregate matches.

## Build the versioned expansion plan

```bash
python3 scripts/research_expansion_builder.py \
  --config config/research_expansion.stage8.v1.json \
  --incidents data/training/research_incidents.stage8.v1.json \
  --positive-queue-out data/training/research_positive_trace_queue.stage8.v1.json \
  --pilot-positive-queue-out data/training/research_pilot_positive_trace_queue.stage8.v1.json \
  --negative-plan-out data/training/research_negative_sampling_plan.stage8.v1.json \
  --index-out data/training/research_expansion_index.stage8.v1.json \
  --report ops/reports/research-expansion-builder.stage8.latest.json
```

The builder must report 20 verified independent event groups, 20 verified
anchor transactions, 15 new positive queue items, and zero held-out overlap.
Records marked `review_hold` do not contribute to those counts.

## Dry-run the positive paid gate

```bash
python3 scripts/historical_trace_replay.py \
  --queue data/training/research_pilot_positive_trace_queue.stage8.v1.json \
  --method trace_transaction \
  --retries 1 \
  --fail-fast \
  --skip-existing \
  --dry-run \
  --run-id stage8-positive-pilot \
  --out ops/reports/research-positive-trace-replay.stage8.pilot.dry-run.json
```

## Sample the negative metadata pilot

The sampler performs only metadata RPC calls; it never calls a trace method.
Start with one block and five candidates. A wider request that cannot load every
requested block must stop before tracing and remain as an audit record.

```bash
python3 scripts/research_negative_sampler.py \
  --config config/research_expansion.stage8.v1.json \
  --incidents data/training/research_incidents.stage8.v1.json \
  --incident-id balancer_2020_06_28 \
  --target-count 5 \
  --max-blocks 1 \
  --out data/training/research_negative_candidates.stage8.pilot.v1.json \
  --queue-out data/training/research_pilot_negative_trace_queue.stage8.v1.json \
  --report ops/reports/research-negative-sampler.stage8.pilot.latest.json
```

Dry-run the resulting queue before paid tracing:

```bash
python3 scripts/historical_trace_replay.py \
  --queue data/training/research_pilot_negative_trace_queue.stage8.v1.json \
  --method trace_transaction \
  --retries 1 \
  --fail-fast \
  --skip-existing \
  --dry-run \
  --run-id stage8-negative-pilot \
  --out ops/reports/research-negative-trace-replay.stage8.pilot.dry-run.json
```

## Run the two paid pilot gates

One positive trace:

```bash
python3 scripts/historical_trace_replay.py \
  --queue data/training/research_pilot_positive_trace_queue.stage8.v1.json \
  --method trace_transaction \
  --retries 1 \
  --fail-fast \
  --skip-existing \
  --run-id stage8-positive-pilot \
  --out ops/reports/research-positive-trace-replay.stage8.pilot.latest.json
```

Five unlabeled negative candidates:

```bash
python3 scripts/historical_trace_replay.py \
  --queue data/training/research_pilot_negative_trace_queue.stage8.v1.json \
  --method trace_transaction \
  --retries 1 \
  --fail-fast \
  --skip-existing \
  --inter-item-delay-s 0.25 \
  --run-id stage8-negative-pilot \
  --out ops/reports/research-negative-trace-replay.stage8.pilot.latest.json
```

Stop immediately on chain mismatch, empty trace, permanent failure, unexpected
method, or provider cost anomaly. JSON-RPC responses do not contain invoice
cost; check the provider dashboard after these calls.

## Hash, parse, enrich, and build the six pilot graphs

```bash
python3 scripts/raw_trace_manifest.py \
  --queue data/training/research_pilot_positive_trace_queue.stage8.v1.json \
  --queue data/training/research_pilot_negative_trace_queue.stage8.v1.json \
  --bundles data/replay/trace-bundle.v1/dt=2026-08-30 \
  --out data/training/raw-trace-manifest.stage8.pilot.v1.json \
  --report ops/reports/raw-trace-manifest.stage8.pilot.latest.json

python3 scripts/trace_parser.py \
  --input data/replay/trace-bundle.v1/dt=2026-08-30 \
  --write-replay \
  --out ops/reports/trace-parser.stage8.pilot.latest.json

python3 scripts/protocol_role_enricher.py \
  --input data/replay/parsed-trace.v1/dt=2026-08-30 \
  --write-replay \
  --out ops/reports/protocol-role-enricher.stage8.pilot.latest.json

python3 scripts/context_window_builder.py \
  --parsed-input data/replay/parsed-trace.v1/dt=2026-08-30 \
  --protocol-features data/replay/protocol-features.v1/dt=2026-08-30 \
  --address-out data/context/address-context.stage8.pilot.v1.json \
  --protocol-out data/context/protocol-context.stage8.pilot.v1.json \
  --report ops/reports/context-window-builder.stage8.pilot.latest.json

python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1/dt=2026-08-30 \
  --protocol-features data/replay/protocol-features.v1/dt=2026-08-30 \
  --address-context data/context/address-context.stage8.pilot.v1.json \
  --protocol-context data/context/protocol-context.stage8.pilot.v1.json \
  --write-replay \
  --write-snapshot \
  --out ops/reports/cash-flow-graph-builder.stage8.pilot.latest.json

python3 scripts/rich_graph_quality_audit.py \
  --exploit-queue data/training/research_pilot_positive_trace_queue.stage8.v1.json \
  --normal-queue data/training/research_pilot_negative_trace_queue.stage8.v1.json \
  --raw-manifest data/training/raw-trace-manifest.stage8.pilot.v1.json \
  --trace-input data/replay/trace-bundle.v1/dt=2026-08-30 \
  --parsed-input data/replay/parsed-trace.v1/dt=2026-08-30 \
  --protocol-input data/replay/protocol-features.v1/dt=2026-08-30 \
  --graph-input data/replay/graph-inference.v1/dt=2026-08-30 \
  --expected-exploit 1 \
  --expected-normal 5 \
  --normal-review-count 5 \
  --out ops/reports/rich-graph-quality-audit.stage8.pilot.latest.json
```

## Screen without promoting the five candidates

```bash
python3 scripts/research_negative_screen.py \
  --config config/research_expansion.stage8.v1.json \
  --queue data/training/research_pilot_negative_trace_queue.stage8.v1.json \
  --incidents data/training/research_incidents.stage8.v1.json \
  --graphs data/replay/graph-inference.v1/dt=2026-08-30 \
  --exploit-corpus /tmp/defihacklabs-main \
  --exploit-corpus-version d7539634f8e48b15829c5716f5618cf1851f27b6 \
  --ofac-sdn /tmp/ofac-sdn-stage8.csv \
  --out data/training/research_negative_screen.stage8.pilot.v1.json \
  --report ops/reports/research-negative-screen.stage8.pilot.latest.json
```

A screen pass means only that no exact match was found in the pinned inputs.
It is not proof of normal behavior and it never promotes a negative label.

## Final pilot audit and acceptance gates

```bash
python3 scripts/research_expansion_audit.py \
  --out ops/reports/research-expansion-audit.stage8.latest.json
```

The pilot passes only when:

- all six traces used `trace_transaction` and succeeded within the retry gate;
- all six trace bundles, parsed traces, feature records, graphs, and raw hashes
  resolve without dangling references;
- the frozen held-out overlap is zero;
- the five negative candidates remain unlabeled and require human review;
- the research target remains explicitly incomplete;
- low protocol-role coverage remains a blocking warning, not a silent pass;
- `stop_after_pilot` prevents automatic paid expansion.

Before the next versioned batch, review the five candidate graphs, inspect the
provider charge, expand the protocol-role dictionary, and obtain explicit batch
authorization. Do not enter Stage 9 until the 100/1,000 promoted graph targets
and the required hard-negative coverage are actually met.
