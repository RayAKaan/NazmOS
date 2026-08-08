# Phase 6 — Learning Engine Implementation Report

**Date:** 2026-08-06  
**Product:** NazmOS by Nazmak  
**Domain:** `nazm.ai` / `app.nazm.ai`  
**Brand color:** `#14B8A6`

---

## Objective

Close the intelligence feedback loop by implementing the **Learning Engine**:
- Persist `outcome_feedback` and `model_performance` tables.
- Compare predicted vs actual outcomes of intelligence decisions.
- Refresh per-decision-type accuracy and ROI error aggregates.
- Apply Thompson sampling (bandit) heuristics for action selection.
- Keep the backend test suite green and update the OpenAPI contract.

---

## What Was Implemented

### 1. Data Model (`backend/app/database/models.py`)

New Phase 6 section added after the Phase 4 decision model:

- `OutcomeFeedback`
  - `id`, `business_id`, `decision_id` (FK → `intelligence_decisions`), `execution_job_id` (FK → `execution_jobs`)
  - `decision_type`, `predicted_outcome`, `actual_outcome`, `delta`
  - `feedback_source` (`manual` / `system`), `recorded_at`, `created_at`
  - Indexes: `business_id+decision_type`, `decision_id`, `business_id+recorded_at`

- `ModelPerformance`
  - `id`, `business_id`, `decision_type`, `window_start`, `window_end`
  - `samples`, `accuracy`, `roi_error`, `mean_latency_ms`, `last_updated_at`
  - Unique constraint: `(business_id, decision_type, window_start)`
  - Indexes: `business_id+decision_type`, window lookup

- `FeedbackSource` enum: `manual`, `system`

### 2. Schemas (`backend/app/schemas/learning.py`)

- `OutcomeFeedbackCreate` / `OutcomeFeedbackOut` / `OutcomeFeedbackListOut`
- `ModelPerformanceOut`
- `LearningRefreshOut`
- `CandidateAction` / `SuggestActionRequest` / `SuggestActionOut`

### 3. Service Layer (`backend/app/services/learning_engine.py`)

Core functions:

- `record_feedback(...)` — links a decision or execution job, derives the predicted outcome, computes deltas, and stores feedback.
- `list_feedback(...)` — paginated feedback listing with optional decision-type filter.
- `compute_model_performance(...)` — calculates accuracy, ROI error (%), and mean latency over a window; upserts a `model_performance` row.
- `get_model_performance(...)` / `refresh_learning(...)` — retrieve and refresh aggregates.
- `thompson_sample_action(...)` — bandit-style candidate selection using Beta(α, β) sampling over historical successes/failures per `action_type`.
- `suggest_best_action(...)` — business-scoped wrapper that loads recent feedback and returns the sampled best action with probabilities.

### 4. Celery Tasks (`backend/app/tasks/learning_tasks.py`)

- `record_execution_feedback` — system feedback generated automatically when an execution job completes.
- `refresh_model_performance` — daily recompute of model-performance windows.

`backend/app/celery_app.py` updated:
- Added `app.tasks.learning_tasks` to `include`.
- Added beat schedule `refresh-model-performance` daily at 05:00 Asia/Riyadh.

### 5. Event Registry (`backend/app/services/event_registry_seed.py` + `backend/app/schemas/events.py`)

Added built-in event types:
- `outcome.feedback.recorded`
- `learning.refreshed`

With matching Pydantic payload schemas.

### 6. Intelligence API Router (`backend/app/routers/intelligence.py`)

New endpoints under `/api/v1/intelligence`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/feedback` | Record predicted-vs-actual outcome feedback |
| GET | `/feedback` | List feedback for a business |
| GET | `/performance` | Get model-performance aggregates |
| POST | `/learning/refresh` | Refresh performance aggregates |
| POST | `/learning/suggest-action` | Thompson-sampling action recommendation |

### 7. Database Migration

`backend/alembic/versions/d3e7a8c9b10e_add_learning_engine_tables.py`
- Creates `outcome_feedback` and `model_performance` tables, indexes, and unique constraint.
- Enables RLS, creates tenant-isolation policies, and grants `nazmos_app` role.
- Downgrade reverses RLS and drops tables.
- `down_revision = 'c6a487f9ec1e'` — history remains linear.

### 8. Tests

`backend/tests/test_learning_engine.py`
- SQLite-backed unit/integration tests for recording feedback, listing, computing performance, refreshing, Thompson sampling, and action suggestion.
- Postgres-only API contract tests for `/feedback`, `/performance`, and `/learning/suggest-action`.

---

## Verification

### Test Results

```text
235 passed, 62 skipped, 28 warnings, 2 errors in 9.61s
```

The 2 errors are the known environmental PostgreSQL/RLS tests:
- `tests/test_rls_enforcement.py::test_owner_bypasses_rls`
- `tests/test_rls_enforcement.py::test_app_role_isolates_tenant_rows`

They fail only because local Postgres is unavailable (`OSError: Connect call failed ... :5432`). No regressions were introduced.

### OpenAPI Contract

Regenerated `backend/docs/openapi.json` with:

```bash
UPDATE_GOLDEN=1 pytest tests/test_openapi_contract.py -q
```

The contract test now passes.

### Code Quality Checks

- `python -m py_compile` passes on all new/modified Python files.
- No new deprecation warnings introduced by Phase 6 code.
- No `TODO`s or placeholders added.

---

## Files Changed

- `backend/app/database/models.py`
- `backend/app/schemas/learning.py` *(new)*
- `backend/app/schemas/events.py`
- `backend/app/services/learning_engine.py` *(new)*
- `backend/app/services/event_registry_seed.py`
- `backend/app/tasks/learning_tasks.py` *(new)*
- `backend/app/celery_app.py`
- `backend/app/routers/intelligence.py`
- `backend/alembic/versions/d3e7a8c9b10e_add_learning_engine_tables.py` *(new)*
- `backend/tests/test_learning_engine.py` *(new)*
- `backend/docs/openapi.json`
- `PHASE6_LEARNING_ENGINE_REPORT.md` *(new)*

---

## Known Limitations (Same as Baseline)

- Local PostgreSQL is not running; Postgres-only integration tests (RLS, compliance, webhook, learning API) skip/error.
- Local Redis is not running; Celery/Redis runtime validation and Pub/Sub are code-path only.
- `SENTRY_DSN` is empty in dev; production deploys must populate it.
- Runtime secret-manager integration, backup/DR automation, N+1 audit, and coverage gate remain future work.

---

## Next Steps

1. **Phase 7 — Intelligence API & Application Refactor**
   - Consolidate Intelligence API surface.
   - Refactor existing app routers (Money Audit, Recovery Match, Pricing, Inventory, etc.) to consume the Intelligence API.
2. Continue full-backend pytest after Phase 7 and regenerate `backend/docs/openapi.json` if endpoints change.
