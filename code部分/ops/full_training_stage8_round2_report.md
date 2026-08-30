# Full Training Stage 8 Round-002 Report

## Outcome

Round-002 is complete. Thirty unique Ethereum Mainnet transactions have
auditable `trace_transaction` bundles and rich graphs: five verified attack
anchors and 25 unlabeled negative candidates. Frozen-test isolation, lineage,
external exact-match screening, and cost guards passed. Labels promoted: zero.

This expands the review pool; it does not complete the research dataset or
authorize Stage 9.

## Batch accounting

- Independent positive events: 5
- Positive rich graphs: 5
- Unlabeled negative rich graphs: 25
- Hard-negative candidates: 7
- Unique paid trace transactions: 30
- Trace attempts: 31
- Reused successful bundles: 1
- `debug_traceTransaction` attempts: 0
- Frozen held-out overlap: 0

Across the Stage 8 pilot and round-002, six unpromoted positive graphs and 30
unpromoted negative candidates now exist, including nine hard-negative
candidates. The formal promoted-label snapshot remains 5 positive and 50
negative; research target gaps therefore remain 95 and 950 until evidence
review and label promotion occur.

## Controlled failures and recovery

The first Lendf.Me metadata block contained zero transactions. The sampler
stopped before trace, retained the failure report, and a single explicit offset
outside the incident exclusion window supplied five candidates.

The first positive replay traced Dough Finance and then stopped after two
truncated Indexed Finance receipt responses. A direct transport diagnostic
retrieved the complete 299,343-byte receipt. The Python client was updated to
request identity encoding and close the HTTP connection; the same queue then
resumed and reused the existing Dough bundle. No sample was replaced.

The 25-negative replay completed with one allowed retry after a transient
connection close. No permanent trace failure remained.

## Graph and screening results

- Successful calls: 2,507
- ERC-20 transfers: 394
- ERC-721 transfers: 10
- Call edges: 2,507
- Transfer edges: 404
- Context edges: 148
- Maximum call depth: 21
- Positive structural reviews: 5/5
- Stratified negative structural reviews: 10/25
- Quality audit errors: 0

All 25 negative candidates had zero exact matches against the pinned 1,320-hash
DeFiHackLabs index, the 91 Ethereum-like OFAC addresses, the cataloged positive
anchors, and the frozen held-out split. They still require analyst review.

Protocol roles were found in four of 30 graphs and only one negative graph.
Consequently, unmatched negatives are candidate data, not protocol-matched
research negatives. One-hour protocol context is also unavailable for this
isolated historical batch and remains explicit in feature-missing flags.

## Acceptance result

Final status: `batch_ok_review_pending_target_incomplete`.

The next gate is analyst review of the six positive and 30 negative accumulated
Stage 8 graphs, followed by protocol-matched filtering and a new versioned label
promotion audit. Ambiguous items remain unlabeled. No additional paid batch or
Stage 9 experiment should start before that gate is complete.
