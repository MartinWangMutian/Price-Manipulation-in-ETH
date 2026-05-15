# Course Submission Summary

## Scope

This submission uses the provider-only and local replay evidence already
generated in the repository. It intentionally excludes work that would require
paid trace APIs or a local Ethereum archive node.

## Included Evidence

- Provider-only shadow pipeline status
- Local pending replay and trace audit reports
- Cash-flow graph, risk, alert, RAG explanation, console, offline evaluation,
  and failure drill reports
- Secret audit for generated reports
- Phase B handoff and completion audit

## Excluded From Scope

- `debug_traceTransaction` / `trace_transaction` historical replay
- Trace-backed label promotion
- Training-dataset readiness from promoted trace labels
- Production contacts, failover drill, and go/no-go launch approval

## Refresh Command

```bash
python3 scripts/phase_b_refresh.py \
  --out ops/reports/phase-b-refresh.latest.json
```

The command refreshes local reports and does not call live trace endpoints.
