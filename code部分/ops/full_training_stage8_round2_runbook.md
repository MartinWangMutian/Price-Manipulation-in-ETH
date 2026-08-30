# Full Training Stage 8 Round-002 Runbook

## Scope

Round-002 is a bounded continuation of Stage 8. It collects five verified
positive anchors and 25 metadata-matched, unlabeled negative candidates. It
does not promote labels, complete the 100/1,000 research target, open the frozen
held-out split, or authorize Stage 9.

## Cost and method guards

From `code部分/`:

```bash
set -a
source ../.env.local
set +a
export ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"
export HISTORICAL_TRACE_METHOD="trace_transaction"
```

The provider usage limit must be set before starting. Every replay uses
`--method trace_transaction --retries 1 --fail-fast --skip-existing`. The batch
config caps unique trace transactions at 30 and has `stop_after_batch=true`.

## Build the positive batch

```bash
python3 scripts/research_batch_builder.py
```

The first pass must return `ready_for_negative_sampling`, five positive items,
and zero frozen held-out overlap.

## Sample five negatives for each frozen event

Run `research_negative_sampler.py` once per incident from
`config/research_batch.stage8.round-002.v1.json`, with `--target-count 5` and
`--max-blocks 1`, using distinct output, queue, and report paths. The sampler
performs metadata calls only and must report `trace_calls_performed=0`.

If a block is unusable, preserve the failed report. A corrected attempt may use
one explicit offset outside the 7,200-block incident exclusion window:

```bash
python3 scripts/research_negative_sampler.py \
  --incident-id lendfme_2020_04_19 \
  --target-count 5 \
  --max-blocks 1 \
  --block-offset -11000 \
  --out data/training/research_negative_candidates.stage8.round-002.lendfme.corrected.v1.json \
  --queue-out data/training/research_negative_trace_queue.stage8.round-002.lendfme.corrected.v1.json \
  --report ops/reports/research-negative-sampler.stage8.round-002.lendfme.corrected.latest.json
```

Finalize the two combined queues by passing the five successful per-event
negative queues as repeated `--negative-queue` arguments to
`research_batch_builder.py`. The status must be `ready_for_paid_dry_run` with
5/25 records and zero labels.

## Dry-run and paid replay

Dry-run both combined queues first. Then replay the five positives. Do not start
the negative gate unless every positive succeeds. If a run stops after a
transient transport failure, preserve its report, fix the transport issue, and
resume the same queue with `--skip-existing`; do not substitute a transaction.

After the positive gate passes, replay the 25 negative candidates with a
0.25-second item delay. Stop on any permanent failure.

## Build and audit round-002 graphs

The canonical partition is `dt=2026-08-30/hour=13`. Hash the raw responses with
`raw_trace_manifest.py`, audit the exact partition with
`trace_bundle_audit.py`, then run:

```bash
python3 scripts/trace_parser.py \
  --input data/replay/trace-bundle.v1/dt=2026-08-30/hour=13 \
  --write-replay \
  --out ops/reports/trace-parser.stage8.round-002.latest.json

python3 scripts/protocol_role_enricher.py \
  --input data/replay/parsed-trace.v1/dt=2026-08-30/hour=13 \
  --write-replay \
  --out ops/reports/protocol-role-enricher.stage8.round-002.latest.json

python3 scripts/context_window_builder.py \
  --parsed-input data/replay/parsed-trace.v1/dt=2026-08-30/hour=13 \
  --protocol-features data/replay/protocol-features.v1/dt=2026-08-30/hour=13 \
  --address-out data/context/address-context.stage8.round-002.v1.json \
  --protocol-out data/context/protocol-context.stage8.round-002.v1.json \
  --report ops/reports/context-window-builder.stage8.round-002.latest.json

python3 scripts/cash_flow_graph_builder.py \
  --parsed-input data/replay/parsed-trace.v1/dt=2026-08-30/hour=13 \
  --protocol-features data/replay/protocol-features.v1/dt=2026-08-30/hour=13 \
  --address-context data/context/address-context.stage8.round-002.v1.json \
  --protocol-context data/context/protocol-context.stage8.round-002.v1.json \
  --write-replay \
  --write-snapshot \
  --out ops/reports/cash-flow-graph-builder.stage8.round-002.latest.json
```

Run `rich_graph_quality_audit.py` with exact 5/25 expectations and a ten-record
normal review sample. Errors must be zero. Low protocol-role coverage remains a
warning and blocks label promotion for unmatched negatives.

## External screen, review packets, and final audit

Screen all 25 negatives against the pinned DeFiHackLabs tree, the hashed OFAC
SDN input, positive anchors, and the frozen held-out split. A screen pass is not
proof that a transaction is benign.

Build the positive and negative analyst packets with:

- `scripts/research_positive_review_packet.py`
- `scripts/research_negative_review_packet.py`

Every review decision starts pending, every label is null, and every promotion
status is `not_promoted`.

Finally run:

```bash
python3 scripts/research_batch_audit.py
```

The accepted status is `batch_ok_review_pending_target_incomplete`. Before a
new batch, analysts must review the six positive anchors and 30 negative
candidates accumulated across the pilot and round-002, retain only justified
protocol-matched negatives, and create a new versioned label snapshot.
