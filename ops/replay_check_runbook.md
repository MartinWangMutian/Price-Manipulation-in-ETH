# Pending Replay Check Runbook

Run this after collecting provider-only pending events:

```bash
python3 scripts/pending_replay_check.py \
  --input data/replay/pending-tx.v1 \
  --out ops/reports/pending-replay-check.latest.json
```

The check verifies:

- replay JSON can be parsed;
- `PendingTxEvent` common fields are present;
- file name matches `event_id`;
- `idempotency_key` equals `chain_id:tx_hash:source`;
- duplicate idempotency keys are reported.

Running the same check repeatedly should not create new replay records or
change the unique event count.

