# Phase 2 — Knowledge Graph Engine Report

**Date:** 2026-08-06
**Branch:** main
**Baseline:** Phase 0 (Event Engine) and Phase 1 (Business Memory Engine) completed and green.

## Summary

Implemented the Knowledge Graph Engine on top of the Phase 0 event stream.
The engine models the business as a connected graph of entities and
relationships in PostgreSQL, using recursive CTEs for expansion and shortest-
path queries. The abstraction is storage-agnostic so Apache AGE or Neo4j can be
swapped in later.

## What was built

### Data model (`backend/app/database/models.py`)

- `GraphEntity` — nodes: `business_id`, `entity_type`, `external_id`, `name`,
  `attributes` (JSON), optional `vector` (JSON array for portability).
- `GraphRelationship` — edges: `source_id`, `target_id`, `relation_type`,
  `strength` (0–1), `evidence_event_ids` (JSON array), `valid_from`,
  `valid_until`.

### Schemas (`backend/app/schemas/knowledge_graph.py`)

- `GraphEntityCreate`, `GraphEntityOut`
- `GraphRelationshipCreate`, `GraphRelationshipOut`
- `GraphExpandOut`, `GraphShortestPathOut`

### Service (`backend/app/services/knowledge_graph.py`)

- `upsert_entity` — create or update a graph node keyed by
  `(business_id, entity_type, external_id)`.
- `upsert_relationship` — create or strengthen an edge; appends evidence event
  ids without duplication.
- `expand_graph` — recursive CTE traversal around a root entity up to a max
  depth, optionally filtered by relation type.
- `shortest_path` — BFS recursive CTE between two entities.
- Event projectors:
  - `supplier.delivered` → `(Supplier)-[:SUPPLIES]->(Product)`
  - `sale.completed` → `(Product)-[:SOLD_MOSTLY_AT]->(Branch)`
  - `employee.clock_in` → `(Employee)-[:WORKS_AT]->(Branch)`

### Router (`backend/app/routers/intelligence.py`)

- `POST /api/v1/intelligence/graph/entities`
- `POST /api/v1/intelligence/graph/relationships`
- `GET /api/v1/intelligence/graph/expand?business_id=...&entity_id=...&depth=...`
- `GET /api/v1/intelligence/graph/shortest-path?business_id=...&from_entity_id=...&to_entity_id=...`

### Integration

- Event processor (`backend/app/services/event_processor.py`) now projects every
  processed event into both business memory (Phase 1) and the knowledge graph
  (Phase 2) atomically before marking it processed.

### Migration

- `backend/alembic/versions/efab679a4d16_add_knowledge_graph_tables.py`
  - Creates `graph_entities` and `graph_relationships`
  - Adds RLS tenant-isolation policies
  - Grants `nazmos_app` role CRUD privileges
  - Linear history: head after `bc6893878598`

### Tests

- `backend/tests/test_knowledge_graph.py`
  - SQLite-backed entity/relationship CRUD tests
  - Event projector test for `sale.completed`
  - Graph expand and shortest-path tests
  - Postgres-only API integration tests (skipped locally)

### OpenAPI contract

- `backend/docs/openapi.json` regenerated with the four new graph endpoints and
  `GraphEntity*` / `GraphRelationship*` schemas.

## LLM / OpenRouter note

No OpenAI API is hardcoded in the backend. `backend/app/config.py` already
routes LLM calls through OpenRouter:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL` (default `https://openrouter.ai/api/v1`)
- `OPENROUTER_SITE_URL`
- `OPENROUTER_APP_NAME`
- `LLM_MODEL` (default `google/gemma-2-9b-it:free`)

`backend/app/services/llm_orchestrator.py` consumes these settings directly and
falls back to rule-based mock responses when `USE_MOCK_LLM=true` or no API key
is configured. Phase 2 does not add any new LLM calls.

## Verification

```text
cd /home/user/NazmOS/backend && pytest -q
212 passed, 52 skipped, 28 warnings, 2 errors in 5.29s
```

- The 2 errors are the known environmental Postgres/RLS failures
  (`tests/test_rls_enforcement.py`) because PostgreSQL is not running locally.
- The 52 skipped tests include Postgres-only integration tests from Phases 0–2.
- Backend boots in SQLite dev mode; `/health` returns 200.
- Alembic head is `efab679a4d16`; history is linear.
- Workspace cleaned of `__pycache__`, `.pyc`, `.pytest_cache`, DB files, and
  empty upload dirs.

## Not solved / Next steps

- Postgres-only integration tests require a running local PostgreSQL instance.
- Redis Pub/Sub and Celery runtime paths are code-verified only (no local Redis).
- Phase 3: Context & Temporal Reasoning engines (`business_context`, timeline,
  `event_derivations`).
