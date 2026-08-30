# Full Training Stage 4 Report

## Outcome

Stage 4 is complete for the engineering-smoke scope. The exact paid-replay
partition was reviewed, labels were frozen, and an event/address-grouped split
was generated and independently audited.

## Label result

- Candidate transactions reviewed: 57
- Promoted positives: 5
- Promoted negatives: 50
- Held as unlabeled: 2
- Hard negatives retained: 6
- Human sign-off claimed: no
- Research-training ready: no

The two unlabeled holds are intentional evidence gates:

- Curve/Vyper candidate `0x4197...b088`: observed on 2023-08-04 with a
  one-call trace, inconsistent with the queued primary attack role for the
  2023-07-30 incident.
- Harvest candidate `0x53fa...8c58`: queued and replayed as an attacker profit
  transfer, not an attack-entry transaction.

## Negative screening

The 50 normal candidates were screened by exact transaction hash against a
pinned DeFiHackLabs checkout and by exact queue endpoint address against the
OFAC SDN dataset. Neither screen produced a hit. The repository stores the
corpus commit, OFAC SHA-256, counts, and per-candidate results, but not the raw
external files.

Exact-match absence is only one evidence gate. These negatives are restricted
to the engineering-smoke scope and are not represented as conclusively benign
research labels.

## Frozen split

| Split | Positive | Negative | Total |
| --- | ---: | ---: | ---: |
| train | 3 | 30 | 33 |
| validation | 1 | 10 | 11 |
| held-out test | 1 | 10 | 11 |

All 46 incident/address groups remain in one split. The independent audit also
checked eleven related normal-transaction pairs and found no cross-split leak.
Positive incident groups also keep their protocol/event identity together. The
current normal graphs contain no protocol-role identifiers to form additional
negative protocol groups; this known coverage limitation remains an explicit
research-readiness blocker rather than being inferred from generic ERC-20 calls.

## Canonical artifacts

- `config/label_review_policy.stage4.v1.json`
- `data/training/label_promotion_decisions.stage4.v1.json`
- `data/training/graph_labels.stage4.v1.json`
- `data/training/label_snapshot.stage4.v1.json`
- `data/training/split_manifest.stage4.v1.json`
- `data/training/splits/stage4/*.v1.json`
- `ops/reports/label-promotion-audit.stage4.latest.json`
- `ops/reports/split-manifest-audit.latest.json`

## Next gate

Stage 5 may use this snapshot for a single-graph forward/backward check and a
single-batch overfit test. No held-out test prediction should be generated in
Stage 5.
