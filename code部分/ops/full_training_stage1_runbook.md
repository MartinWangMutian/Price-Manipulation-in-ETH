# Full Training Stage 1: Safety Gate

This stage is intentionally non-billable. It establishes the immutable pre-run
snapshot and the runtime policy used by later historical replay stages.

## Locked policy

- Chain: Ethereum Mainnet (`chain_id=1`).
- Historical method: `trace_transaction` only in the paid training workflow.
- Retry budget: at most one retry per transaction.
- Failure behavior: stop after the first failed trace.
- Raw provider responses: local-only under `data/raw-trace/`; never commit them.
- Existing unrelated work (`.codex_cv_review/` and the pre-existing ZIP deletion)
  is excluded from training commits.

## Runtime endpoint mapping

Do not copy or print the endpoint value. Load it only in the process that runs
the later replay command:

```bash
set -a
source ../.env.local
set +a
export ETH_MAIN_HTTP_URL="$ETH_PROVIDER_HTTP_URL"
export HISTORICAL_TRACE_METHOD="trace_transaction"
```

## Snapshot command

Run from `code部分/` before any paid replay:

```bash
python3 scripts/training_run_guard.py \
  --env-file ../.env.local \
  --out ops/snapshots/pre-full-training.v1.json
```

The generated manifest contains only presence flags, hashes, counts, Git state,
and report statuses. It never records endpoint values.

## Later paid gates (not part of Stage 1)

1. One exploit transaction with `--limit 1`.
2. Full seven-item exploit queue after the pilot audit.
3. Five normal transactions, then the complete 50-item normal queue.

Every later command must explicitly include `--method trace_transaction`,
`--retries 1`, and `--fail-fast`.
