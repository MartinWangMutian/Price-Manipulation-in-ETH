# Phase B Completion Checklist

Generated from current local reports on 2026-05-15.

## Objective

Finish a course-scope Phase B evidence bundle without paid trace APIs or local
Ethereum node deployment.

## Active Requirements

| Requirement | Evidence | Current status |
| --- | --- | --- |
| Course no-trace scope is recorded | `config/phase_b_scope.json` | Active: `course_no_trace` |
| Provider-only shadow pipeline is healthy | `ops/reports/project-status.latest.json` via `provider_only_shadow_pipeline` | Pass: `ok` |
| Local replay/report surface is present | `ops/reports/project-status.latest.json` report statuses | Pass: pending replay, graph, risk, alert, RAG, console, offline eval, failure drill |
| Generated reports do not expose RPC URL secrets | `ops/reports/report-secret-audit.latest.json` | Pass when latest report returns `status=ok` |
| Handoff/status docs are present | `ops/phase_b_handoff.md`, `ops/status_summary.md`, `ops/course_submission_summary.md` | Pass after refresh |

## Waived For Course Scope

| Waived item | Reason |
| --- | --- |
| `ETH_MAIN_HTTP_URL` | Would require trace-capable paid API or local node |
| Trace endpoint preflight | Same as above |
| Historical trace replay | Same as above |
| Trace-backed label promotion | Depends on historical trace replay |
| Training readiness | Depends on trace-backed labels |
| Production contacts and go/no-go | Operational production concern, not needed for the course submission |

## Refresh Command

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

Completion is measured by
`ops/reports/phase-b-completion-audit.latest.json` under the active
`course_no_trace` scope.
