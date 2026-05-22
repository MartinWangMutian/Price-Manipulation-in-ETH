# Artifact Manifest Runbook

## Purpose

Generate a categorized inventory of local config, schemas, scripts, replay files, reports, and runbooks.

## Command

```bash
python3 scripts/artifact_manifest.py \
  --out ops/reports/artifact-manifest.latest.json
```

The default stdout is intentionally short and prints only counts plus key status
files. Use `--verbose` when you need the full file list in the terminal:

```bash
python3 scripts/artifact_manifest.py \
  --out ops/reports/artifact-manifest.latest.json \
  --verbose
```
