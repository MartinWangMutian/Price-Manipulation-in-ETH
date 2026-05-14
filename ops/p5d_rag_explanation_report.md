# P5-D Evidence-Constrained Explanation Report

## Scope

Implemented local `rag-explanation.v1` generation from alert events.

## Implemented

- Graph summary template
- Document summary template
- Analyst note template
- Evidence refs on factual summary sentences
- Preservation of score, severity, and reason codes from alert events
- RAG timeout path after alert emission
- Explanation audit log

## Current Status

The builder generated 110 provider-only `rag-explanation.v1` records using `--include-low`; production routing should normally run it for high and critical alerts.

Current validation:

- explanations generated/written: 110
- replay check: 110 valid explanations, errors empty
- explanation audit log lines: 220
- timeout drill: 110 simulated timeout explanations, errors empty
- analyst notes preserve alert score, severity, and reason codes
- graph/doc/analyst summaries include inline evidence refs

## Remaining Gap

This is still template-based local generation. Production use needs richer evidence extraction, stricter sentence-level citation validation, and source-section snapshots.
