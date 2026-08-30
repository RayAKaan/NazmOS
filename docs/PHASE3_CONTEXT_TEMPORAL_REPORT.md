# Phase 3 — Context & Temporal Reasoning Engine Report

**Date:** 2026-08-06
**Branch:** main
**Baseline:** Phases 0–2 completed and green.

## Summary

Implemented the Context & Temporal Reasoning Engine. External context
(holidays, weather, inflation, regulation) is fetched via adapters, persisted,
and attached to events at ingestion time. Temporal reasoning provides a
queryable event timeline, a “what changed” summary, and causal-chain explainability
through `event_derivations`.

## What was built

### Data model (`backend/app/database/models.py`)

- `BusinessContext` — external context records:
  `context_type`, `source`, `source_url`, `effective_from/until`, `payload`,
  `confidence`.
- `EventDerivation` — causal/correlational links between events:
  `cause_event_id`, `effect_event_id`, `derivation_type`, `confidence`,
  `evidence`.

### Schemas (`backend/app/schemas/context.py`)

- `BusinessContextCreate`, `BusinessContextOut`
- `EventDerivationCreate`, `EventDerivationOut`
- `TimelineOut`, `WhatChangedOut`, `WhyOut`

### Services

- `backend/app/services/context_engine.py`
  - `create_context`, `get_active_context`, `build_context_snapshot`
  - Adapters with graceful fallback:
    - `fetch_holiday_context` (nager.date API → KSA holiday fallback)
    - `fetch_weather_context` (Open-Meteo API)
    - `fetch_inflation_context` (World Bank API → fallback)
    - `fetch_regulation_context` (MoC RSS feed)
  - `refresh_context_for_business` — refreshes all adapters and persists
    results.

- `backend/app/services/temporal_reasoning.py`
  - `get_timeline` — paginated event timeline.
  - `what_changed` — summary of events since a timestamp with counts.
  - `create_derivation` — record causal links.
  - `why` — recursive CTE causal chain from an event.

### Router (`backend/app/routers/intelligence.py`)

- `POST /api/v1/intelligence/context`
- `GET /api/v1/intelligence/context`
- `POST /api/v1/intelligence/context/refresh`
- `POST /api/v1/intelligence/derivations`
- `GET /api/v1/intelligence/timeline`
- `GET /api/v1/intelligence/what-changed`
- `GET /api/v1/intelligence/why/{event_id}`

### Integration

- `backend/app/services/event_engine.py` now automatically attaches the active
  context snapshot to every ingested event (unless the caller provides one).

### Migration

- `backend/alembic/versions/357f3cbca428_add_context_and_temporal_reasoning_tables.py`
  - Creates `business_context` and `event_derivations`
  - Adds RLS tenant-isolation policies
  - Grants `nazmos_app` role CRUD privileges
  - Linear history: head after `efab679a4d16`

### Tests

- `backend/tests/test_context_temporal.py`
  - SQLite-backed context CRUD and snapshot tests
  - Event ingestion context attachment test
  - Timeline and what-changed tests
  - Causal-chain test
  - Postgres-only API integration tests (skipped locally)

### OpenAPI contract

- `backend/docs/openapi.json` regenerated with the new context/temporal
  endpoints and schemas.

## Verification

```text
cd /home/user/NazmOS/backend && pytest -q
218 passed, 54 skipped, 28 warnings, 2 errors in 6.53s
```

- The 2 errors are the known environmental Postgres/RLS failures
  (`tests/test_rls_enforcement.py`) because PostgreSQL is not running locally.
- The 54 skipped tests include Postgres-only integration tests from Phases 0–3.
- Backend boots in SQLite dev mode; `/health` returns 200.
- Alembic head is `357f3cbca428`; history is linear.
- Workspace cleaned of `__pycache__`, `.pyc`, `.pytest_cache`, DB files, and
  empty upload dirs.

## Not solved / Next steps

- Postgres-only integration tests require a running local PostgreSQL instance.
- Redis Pub/Sub and Celery runtime paths are code-verified only (no local Redis).
- Phase 4: Decision & Explainability Engine (`intelligence_decisions`, scoring
  functions).
