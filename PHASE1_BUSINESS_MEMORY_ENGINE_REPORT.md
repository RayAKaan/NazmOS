# Phase 1 — Business Memory Engine Report

**Date:** 2026-08-06
**Branch:** main
**Baseline:** Phase 0 Universal Event Engine completed and green.

## Summary

Implemented the Business Memory Engine on top of the Phase 0 event stream.
The engine maintains a living, queryable projection of business state in
PostgreSQL JSONB documents and writes an audit log for every mutation.

## What was built

### Data model (`backend/app/database/models.py`)

- `BusinessMemory` — one JSONB document per `(business_id, memory_type)`.
  Supported memory types (enum `MemoryType`):
  - `current_state`
  - `forecasts`
  - `goals`
  - `patterns`
  - `seasonality`
  - `failures`
  - `relationships`
- `MemoryUpdate` — append-only audit of every memory mutation (event id, path,
  old value, new value, timestamp).

### Schemas (`backend/app/schemas/business_memory.py`)

- `BusinessMemoryOut`
- `GoalSetRequest`
- `MemoryUpdateOut`
- `MemoryChangesOut`

### Service (`backend/app/services/business_memory.py`)

- `get_or_create_memory`, `get_memory`, `set_memory_path`, `set_goals`
- Idempotent event projectors:
  - `inventory.changed` → current stock + reorder flag
  - `sale.completed` → daily/branch sales totals + top-product patterns
  - `supplier.delivered` → supplier reliability signals
  - `price.updated` → pricing history (last 20 points)
- `route_event_to_projectors` — dispatches events to projectors
- `replay_events_to_memory` — deterministic rebuild for property tests / DR
- `list_memory_changes` — paginated audit log

### Router (`backend/app/routers/intelligence.py`)

- `GET /api/v1/intelligence/memory/{memory_type}?business_id=...`
- `PATCH /api/v1/intelligence/memory/goals?business_id=...`
- `GET /api/v1/intelligence/memory/changes?business_id=...&memory_type=...`

### Celery tasks (`backend/app/tasks/business_memory_tasks.py`)

- `update_business_memory(event_id)`
- `rebuild_business_memory(business_id)`

### Integration

- Event processor (`backend/app/services/event_processor.py`) now projects every
  processed event into business memory atomically before marking it processed.
- Celery app includes `app.tasks.business_memory_tasks`.
- `app/main.py` registers the new intelligence router.

### Migration

- `backend/alembic/versions/bc6893878598_add_business_memory_engine_tables.py`
  - Creates `business_memory` and `memory_updates`
  - Adds RLS tenant-isolation policies
  - Grants `nazmos_app` role CRUD privileges
  - Linear history: head after `969ef7949298`

### Tests

- `backend/tests/test_business_memory.py`
  - Pure unit tests for path helpers, delta detection, UUID normalization
  - SQLite-backed projector tests for inventory, sales, pricing, goals
  - Deterministic replay property test
  - Postgres-only API integration tests (skipped locally)

### OpenAPI contract

- `backend/docs/openapi.json` regenerated with the three new intelligence
  endpoints and `BusinessMemory*` schemas.

## Verification

```text
pytest -q
206 passed, 50 skipped, 28 warnings, 2 errors in 4.63s
```

- The 2 errors are the known environmental Postgres/RLS failures
  (`tests/test_rls_enforcement.py`) because PostgreSQL is not running locally.
- The 50 skipped tests include Postgres-only integration tests from Phase 0
  and Phase 1.
- Frontend build/lint status was not changed by this backend phase.
- Backend boots in SQLite dev mode; `/health` returns 200; `/api/v1/ready`
  returns 200 degraded because Redis is missing.

## Not solved / Next steps

- Postgres-only integration tests require a running local PostgreSQL instance.
- Redis Pub/Sub and Celery runtime paths are code-verified only (no local Redis).
- Phase 2: Knowledge Graph (`graph_entities`, `graph_relationships`).
- Phase 3: Context & Temporal Reasoning engines.
