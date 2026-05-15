# Phase B User Action Packet

## Current Scope

This project is now in course assignment scope:

- Do not buy paid trace API access.
- Do not deploy or maintain a local Ethereum archive node.
- Do not run historical trace replay.
- Treat production on-call contacts, trace-backed label promotion, training readiness, and production go/no-go as out of scope.

The scope policy is recorded in `config/phase_b_scope.json`.

## Current Action

No trace endpoint action is needed.

Refresh the local evidence bundle when files change:

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

Then use:

- `ops/status_summary.md`
- `ops/phase_b_completion_checklist.md`
- `ops/course_submission_summary.md`

## Optional Only

`config/ops_contacts.local.json` can remain placeholder-only for this course
scope. It is ignored by git and is no longer a blocker.
