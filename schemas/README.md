# Event Schemas

Phase 1 schemas are JSON Schema draft 2020-12 documents. All event schemas
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

Schema validation in Phase 1 can start with JSON parsing and required-field
checks. A full JSON Schema validator should be added when project dependencies
are introduced.

