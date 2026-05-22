# Replay Label Candidates Runbook

## Purpose

Maintain candidate exploit transaction hashes and the normal complex transaction
sampling strategy before labels are promoted into model training.

The candidate file is intentionally not treated as a confirmed training label
source. Transactions must be replayed through a Geth or Erigon trace endpoint and
reviewed before promotion.

## Command

```bash
python3 scripts/replay_label_candidates_check.py \
  --candidates data/training/replay_label_candidates.seed.json \
  --incidents data/training/positive_incidents.seed.json \
  --normal-candidates data/training/normal_replay_candidates.seed.json \
  --out ops/reports/replay-label-candidates-check.latest.json
```

## Promotion Criteria

- The transaction hash is linked to the incident by at least one credible source.
- The transaction is trace-replayed on Ethereum mainnet.
- The resulting graph has rich call/transfer edges, not provider-only fallback.
- An analyst confirms the candidate role: `attack_tx`, `setup_tx`,
  `attacker_flow_tx`, or `attacker_profit_transfer_tx`.
- Normal complex candidate transactions must be trace-replayed, screened against
  known incident/sanctions/exploit labels, and analyst-promoted before training.
