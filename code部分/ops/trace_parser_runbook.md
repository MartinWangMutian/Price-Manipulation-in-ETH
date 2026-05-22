# Trace Parser Runbook

## Purpose

Phase 3-A parser that converts `trace-bundle.v1` replay records into normalized call and transfer features for the later cash-flow graph builder.

## Inputs

- `data/replay/trace-bundle.v1/**.json`
- `config/selector_dictionary.json`
- `config/token_metadata_cache.example.json`

## Commands

Run the synthetic parser self-test:

```bash
python3 scripts/trace_parser_selftest.py
```

Parse current trace replay records and write parsed replay records:

```bash
python3 scripts/trace_parser.py \
  --input data/replay/trace-bundle.v1 \
  --write-replay \
  --out ops/reports/trace-parser.latest.json
```

## Provider-only note

Provider fallback trace bundles have no raw call tree and no logs, so the parser should produce valid empty parsed records with `trace_unsupported`, `no_logs`, and `no_calls` feature flags. Real transfer and call coverage requires a Geth or Erigon trace endpoint.
