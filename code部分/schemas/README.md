# Event Schemas

Phase 1 schemas are JSON Schema draft 2020-12 documents. The six event schemas
include:

- `event_id`
- `schema_ver`
- `chain_id`
- `created_at`
- `idempotency_key`

## Schemas

| Topic | Schema |
|---|---|
| `pending-tx.v1` | `pending-tx.v1.schema.json` |
| `trace-bundle.v1` | `trace-bundle.v1.schema.json` |
| `graph-inference.v1` | `graph-inference.v1.schema.json` |
| `risk-score.v1` | `risk-score.v1.schema.json` |
| `alert-event.v1` | `alert-event.v1.schema.json` |
| `rag-explanation.v1` | `rag-explanation.v1.schema.json` |
| auxiliary RAG document | `rag-document.v1.schema.json` |

`scripts/validate_schemas.py` checks the topic metadata and validates every
committed replay record for the six event topics, plus the seeded RAG documents.
It implements the JSON Schema keywords used by this repository without adding a
runtime dependency.
