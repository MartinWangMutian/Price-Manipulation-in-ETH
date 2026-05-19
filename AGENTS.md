# Repository Guidelines

## Project Structure & Module Organization

This repository supports blockchain finance risk monitoring, replay analysis,
and operational reporting. Core Python entry points live in `scripts/`; most
scripts are standalone CLIs and many have a paired `*_selftest.py`. Runtime and
policy configuration lives in `config/`, JSON schemas in `schemas/`, runbooks
and generated reports in `ops/`, planning notes in `plan/`, and replay/training
fixtures under `data/`. Presentation artifacts and generated deliverables are in
`ppt/` and `outputs/`; treat these as output-heavy areas unless a task is
explicitly about the deck or exported artifact.

## Build, Test, and Development Commands

This project is primarily Python and currently has no root package manifest.
Use Python 3.12 where possible; a local `.venv312/` may already exist.

- `python3 scripts/alert_orchestrator_selftest.py`: run a focused synthetic
  check for one script.
- `for t in scripts/*_selftest.py; do python3 "$t"; done`: run all available
  self-tests.
- `python3 scripts/env_local_audit.py --env-file .env.local --out ops/reports/env-local-audit.latest.json`:
  audit local environment inputs.
- `python3 scripts/status_summary.py --out ops/reports/status-summary.latest.json`:
  refresh the operational status summary.

See `ops/command_index.md` for stage-specific replay, graph, RAG, alerting, and
audit commands.

## Coding Style & Naming Conventions

Follow PEP 8 Python style: 4-space indentation, `snake_case` functions and
variables, `CamelCase` classes, and short CLI-oriented modules. Prefer standard
library modules already used here: `argparse`, `json`, `pathlib`, `datetime`,
and typed containers from `typing`. Keep JSON output deterministic with
`indent=2`, `sort_keys=True`, UTF-8 encoding, and a trailing newline.

## Testing Guidelines

Add or update a sibling `*_selftest.py` when changing a script. Self-tests should
use small in-memory fixtures, plain `assert` statements, and print a short
`<name> ok` message on success. For data-pipeline changes, also run the relevant
check command against `data/replay/` or `data/training/` and write reports to
`ops/reports/`.

## Commit & Pull Request Guidelines

Recent commits use short Chinese summaries, for example `论文大纲` and
`完成phase0，1`. Keep commit subjects concise and task-focused. In PRs, include
the purpose, changed scripts/configs, commands run, and any generated report
paths. Link related issues or runbooks, and include screenshots only for
`ppt/` or visual `outputs/` changes.

## Security & Configuration Tips

Do not commit secrets. `.env.local` and `config/ops_contacts.local.json` are
ignored; keep examples in `config/*.example.json` or `ops/*.env.example`.
Run `python3 scripts/report_secret_audit.py --input ops/reports --out ops/reports/report-secret-audit.latest.json`
before sharing generated reports.
