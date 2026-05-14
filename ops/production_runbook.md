# Production Runbook

## Mode

Provider-only shadow mode. No automatic on-chain execution is allowed.

## Daily Checks

- Review false positive candidates.
- Review false negative candidates when labeled replay data exists.
- Review trace failures and `trace_unsupported` rates.
- Review RAG null retrieval rate.
- Review high/critical handling outcomes.

## Weekly Checks

- Review threshold profile.
- Review runbook changes.
- Review model drift metrics when training data is ready.
- Review label authorization and RAG document updates.

## Escalation

Use the on-call approval runbook. Any chain action remains a suggested unsigned action until approved by a named approver.
