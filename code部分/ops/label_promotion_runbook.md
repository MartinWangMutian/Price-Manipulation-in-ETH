# Stage 4 Label Promotion and Data Freeze Runbook

## Purpose

Track evidence-gated decisions for candidate exploit and normal transactions
after historical trace replay and strict rich-graph audit. The original seed
file remains unchanged. Stage 4 produces a separate engineering-smoke snapshot
and never represents agent-assisted review as human sign-off.

## Prerequisites

- `ops/reports/rich-graph-quality-audit.latest.json` is `ok` with zero errors.
- The paid replay, trace bundle, and graph partition all contain the exact 57
  queued transactions.
- A local checkout of the public DeFiHackLabs corpus and a current OFAC SDN CSV
  are available outside the repository. Raw external files are not committed.

## Build evidence-gated decisions

```bash
python3 scripts/stage4_label_review_builder.py \
  --exploit-corpus /path/to/DeFiHackLabs \
  --ofac-sdn /path/to/SDN.CSV
```

The committed decision artifact stores the DeFiHackLabs commit, OFAC file hash,
screening counts, exact-match outcomes, trace/graph references, and review
scope. It does not store either external raw dataset.

The current review promotes five event-linked malicious graphs and all fifty
screened normal candidates for the engineering smoke dataset. The Curve/Vyper
candidate is held because its replay timestamp and one-call trace do not support
the queued primary-attack role. The Harvest candidate is held because it is an
attacker profit transfer rather than an attack-entry transaction.

## Audit and export labels

```bash
python3 scripts/label_promotion_audit.py \
  --decisions data/training/label_promotion_decisions.stage4.v1.json \
  --out ops/reports/label-promotion-audit.stage4.latest.json

python3 scripts/graph_label_exporter.py \
  --decisions data/training/label_promotion_decisions.stage4.v1.json \
  --graphs data/replay/graph-inference.v1/dt=2026-08-29 \
  --out data/training/graph_labels.stage4.v1.json \
  --report ops/reports/graph-label-exporter.stage4.latest.json
```

## Build and audit the frozen split

```bash
python3 scripts/grouped_split_builder.py
python3 scripts/split_manifest_audit.py
```

Positive samples are grouped by incident. Negative samples are grouped into
connected components when they share a non-ubiquitous address from the queued
endpoints or rich graph within the configured 15-minute context window. The
held-out test split is frozen before training and must be evaluated only once
after the model, hyperparameters, and threshold are frozen.

The rich-graph audit found no protocol-role identifiers on the normal cohort,
so the builder does not invent protocol membership from generic token calls.
This prevents false grouping claims and remains a research-readiness blocker.

Current frozen counts:

| Split | Positive | Negative | Total |
| --- | ---: | ---: | ---: |
| train | 3 | 30 | 33 |
| validation | 1 | 10 | 11 |
| held-out test | 1 | 10 | 11 |

## Interpretation boundary

`engineering_smoke_training_ready=true` means the snapshot can validate data
loading, optimization, checkpointing, and inference consistency. It does not
mean the model is research-ready. Research training remains blocked until the
dataset and human evidence review reach the minimums in the full training plan.
