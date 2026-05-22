# Phase B Handoff

## Current Scope

Phase B is now scoped as a course assignment, not a production launch:

- Scope policy: `config/phase_b_scope.json`
- Mode: `course_no_trace`
- Paid trace APIs: not allowed
- Local Ethereum archive node: not required
- Historical trace replay: waived

## Current State

- Provider-only shadow pipeline: ok
- Label queue readiness: trace_ready, retained as backlog evidence only
- Exploit trace queue: 7 transactions
- Normal trace queue: 50 transactions
- Historical trace results: waived for course scope
- Training ready: waived for course scope
- Provider trace probe: degraded on free endpoint, no longer a blocker
- Report secret audit: must remain `ok`
- Production go/no-go: out of scope

## Evidence Bundle

Use these files for the course handoff:

- `ops/status_summary.md`
- `ops/phase_b_completion_checklist.md`
- `ops/course_submission_summary.md`
- `ops/reports/phase-b-completion-audit.latest.json`
- `ops/reports/report-secret-audit.latest.json`

## Refresh

Run this after changing local reports or docs:

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

The refresh does not call live trace endpoints.
