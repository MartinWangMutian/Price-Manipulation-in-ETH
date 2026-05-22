# Status Summary Runbook

## Purpose

Generate a concise Markdown page that summarizes provider-only shadow status,
go/no-go readiness, metric gaps, missing external inputs, blockers, and artifact
counts.

## Command

```bash
python3 scripts/status_summary.py \
  --out ops/status_summary.md
```

Run this after regenerating readiness reports, project status, and the artifact
manifest.
