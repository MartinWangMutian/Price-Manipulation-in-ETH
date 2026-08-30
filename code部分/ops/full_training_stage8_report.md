# Full Training Stage 8 Report

## Outcome

The Stage 8 research-expansion pipeline and its cost-bounded pilot are
complete. The research-scale dataset is not complete, so Stage 9 formal
experiments are not authorized.

The pipeline now provides a versioned incident evidence catalog, positive
trace queue, per-event negative sampling plan, metadata sampler, external
exact-match screen, frozen-test isolation checks, and a final stop-gate audit.
No labels were promoted automatically.

## Research target accounting

| Gate | Current | Target | Status |
|---|---:|---:|---|
| Verified independent attack events | 20 | 20 | met |
| Promoted positive rich graphs | 5 | 100 | gap: 95 |
| Promoted negative rich graphs | 50 | 1,000 | gap: 950 |
| New verified positive anchor queue | 15 | supporting input | ready, not fully replayed |
| Negative sampling slots | 1,000 | 1,000 | planned, not collected |

The catalog contains 22 incident records: 20 `verified_anchor` groups and two
`review_hold` records. The held records do not count toward the verified-event
gate. A verified anchor is evidence for an event and a candidate transaction;
it is not itself a promoted training label.

## Paid pilot

The pilot made six `trace_transaction` calls after dry-run validation:

- one verified Balancer attack anchor;
- five time/gas/input/value-matched contract-call candidates from a historical
  block outside the configured incident exclusion window.

All six trace calls succeeded on the first attempt. The positive trace contains
653 successful calls and 315 decoded ERC-20 transfers. The five negative
candidates contain 144 calls and three decoded transfers in total. The complete
pilot produced six trace bundles, six parsed traces, six protocol feature
records, and six rich graphs with 797 Call edges and 318 Transfer edges.

One earlier 10-block metadata sampling attempt received only four successful
block responses and stopped before any trace call. The corrected one-block
pilot loaded its single block and selected five distinct destination-address
candidates. That failed attempt is retained as audit evidence rather than
silently discarded.

The provider response exposes request results and latency, not invoice cost.
The exact charge must be checked in the provider billing dashboard before any
larger paid batch.

## Candidate screening and label safety

The five negative candidates were screened against:

- 1,320 transaction hashes indexed from the pinned DeFiHackLabs source tree;
- 91 Ethereum-like addresses parsed from the downloaded OFAC SDN file;
- all cataloged positive anchors and the frozen Stage 4 held-out manifest.

Exact matches found: zero. Two graphs meet the configured hard-negative
complexity rule. These facts make them review candidates only; they do not
prove benign behavior. Human review is still pending and labels promoted in
Stage 8 remain zero.

The external source trees and raw SDN file stayed under `/tmp`. Only source
references, pinned versions, SHA-256 hashes, aggregate counts, and match counts
are recorded in repository artifacts.

## Graph quality and remaining blocker

Structural lineage and content checks passed for all six graphs:

- expected transaction, raw-trace, parsed-trace, feature, and graph references
  resolve;
- call and transfer counts are preserved through graph construction;
- graph snapshots match replay records;
- feature and builder versions are present;
- frozen held-out overlap is zero.

Protocol-role coverage is zero of six graphs. The current dictionary loaded ten
role contracts but matched none of the pilot addresses. This is an explicit
research-grade blocker: the five candidates must not be promoted and the next
large batch must not start until role coverage is expanded and re-audited.
Context-window records are also marked unavailable/empty for this isolated
historical pilot and remain visible through feature-missing flags.

## Isolation and cost controls

- Trace method: `trace_transaction` only
- `debug_traceTransaction` calls: zero
- Maximum retries: one
- Fail-fast: enabled
- Existing successful bundles: reusable without repaying
- Frozen held-out hashes: 11
- New pilot/full-queue overlaps with frozen held-out: zero
- Labels promoted: zero
- Automatic continuation after pilot: disabled
- Raw provider responses committed: no

## Verification

- Stage 8 builder, sampler, screen, and final-audit selftests passed.
- Final Stage 8 audit status: `pilot_ok_target_incomplete`.
- Rich graph quality audit errors: zero.
- External screen errors: zero.
- All repository selftests passed.
- Repository schema checks and dependency checks passed.
- Secret and whitespace checks passed.

## Canonical evidence

- `config/research_expansion.stage8.v1.json`
- `data/training/research_incidents.stage8.v1.json`
- `data/training/research_expansion_index.stage8.v1.json`
- `ops/reports/research-expansion-builder.stage8.latest.json`
- `ops/reports/research-positive-trace-replay.stage8.pilot.latest.json`
- `ops/reports/research-negative-sampler.stage8.pilot.latest.json`
- `ops/reports/research-negative-trace-replay.stage8.pilot.latest.json`
- `ops/reports/rich-graph-quality-audit.stage8.pilot.latest.json`
- `ops/reports/research-negative-screen.stage8.pilot.latest.json`
- `ops/reports/research-expansion-audit.stage8.latest.json`
- `ops/full_training_stage8_runbook.md`

## Next gate

Before any new paid batch:

1. inspect the six-call pilot charge in the provider billing dashboard;
2. manually review all five negative candidates and preserve uncertain items as
   unlabeled;
3. expand and verify protocol-role coverage;
4. create a new versioned batch manifest and authorize its bounded size.

Stage 8 remains active until at least 100 promoted positive and 1,000 promoted
negative rich graphs exist with hard-negative coverage. Stage 9 model search,
five-seed training, ablations, and frozen evaluation must wait.
