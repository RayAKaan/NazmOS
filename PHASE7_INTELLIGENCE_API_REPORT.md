# Phase 7 — Intelligence API & Application Refactor Report

**Date:** 2026-08-06  
**Product:** NazmOS by Nazmak  
**Domain:** `nazm.ai` / `app.nazm.ai`  
**Brand color:** `#14B8A6`

---

## Objective

Consolidate all intelligence engines behind a single, typed **Intelligence API**
and begin migrating NazmOS applications to consume it. Add the Phase 7 endpoints
specified in `NAZMOS_INTELLIGENCE_ARCHITECTURE_PLAN.md`:

- `POST /api/v1/intelligence/analyze`
- `POST /api/v1/intelligence/predict`
- `POST /api/v1/intelligence/explain`
- `POST /api/v1/intelligence/plan`
- `POST /api/v1/intelligence/simulate` *(already existed, retained)*
- `POST /api/v1/intelligence/execute` *(already existed, retained)*
- `POST /api/v1/intelligence/observe`
- `POST /api/v1/intelligence/remember`
- `POST /api/v1/intelligence/reason`

---

## What Was Implemented

### 1. Unified Intelligence API Service (`backend/app/services/intelligence_api.py`)

A single service module that routes to the underlying engines:

- `analyze(...)` — loads memory snapshot, graph evidence, context evidence, recent events, and generates a decision.
- `predict(...)` — sales/demand/stock predictions from business memory using simple weighted averages.
- `explain(...)` — decision explainability wrapper.
- `plan(...)` / `simulate(...)` / `execute(...)` — thin wrappers around Phase 5 engines.
- `observe(...)` — ingests an event through the Universal Event Engine.
- `remember(...)` — writes to business memory or goals.
- `reason(...)` — answers a natural-language question with a decision and optional plan.

### 2. Internal Client (`backend/app/services/intelligence_api_client.py`)

`IntelligenceAPIClient(session, business_id)` lets existing application routers
consume the Intelligence API directly (same process, no HTTP overhead) using the
same surface as the public endpoints.

### 3. Schemas (`backend/app/schemas/intelligence_api.py`)

Typed request/response models for all nine Phase 7 operations, reusing existing
`DecisionOut`, `PlanOut`, `SimulationOut`, `ExecutionJobOut`, `EventIngest`, and
`DecisionExplainOut` schemas where possible.

### 4. Intelligence Router (`backend/app/routers/intelligence.py`)

Added Phase 7 endpoints under `/api/v1/intelligence`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/analyze` | Cross-engine business analysis |
| POST | `/predict` | Sales / demand / stock prediction |
| POST | `/explain` | Explain a decision |
| POST | `/plan` | Goal-driven plan (unified alias) |
| POST | `/observe` | Ingest and process an event |
| POST | `/remember` | Write memory or goals |
| POST | `/reason` | Natural-language reasoning |

Existing Phase 0–6 endpoints (`/plans`, `/simulate`, `/execute`, `/decisions/*`,
`/memory/*`, `/graph/*`, `/context/*`, `/feedback`, `/learning/*`, etc.) remain
unchanged for backward compatibility.

### 5. Application Refactor Example (`backend/app/routers/dashboard.py`)

Added `GET /api/v1/dashboard/intelligence-summary`, which consumes the
`IntelligenceAPIClient.analyze(...)` method instead of raw SQL. This proves the
migration pattern: existing apps can call the Intelligence API while legacy
endpoints remain intact.

### 6. Tests

`backend/tests/test_phase7.py`
- SQLite-backed tests for `analyze`, `predict`, `observe`, `remember`, `reason`, and `explain`.
- Postgres-only API contract tests for `/analyze`, `/predict`, `/reason`, and `/dashboard/intelligence-summary`.

---

## Verification

### Test Results

```text
241 passed, 66 skipped, 28 warnings, 2 errors in 10.60s
```

The 2 errors are the known environmental PostgreSQL/RLS tests:
- `tests/test_rls_enforcement.py::test_owner_bypasses_rls`
- `tests/test_rls_enforcement.py::test_app_role_isolates_tenant_rows`

They fail only because local Postgres is unavailable. No regressions were introduced.

### OpenAPI Contract

Regenerated `backend/docs/openapi.json` with:

```bash
UPDATE_GOLDEN=1 pytest tests/test_openapi_contract.py -q
```

The contract test now passes.

### Code Quality Checks

- `python -m py_compile` passes on all new/modified Python files.
- No new deprecation warnings introduced by Phase 7 code.
- No `TODO`s or placeholders added.

---

## Files Changed

- `backend/app/services/intelligence_api.py` *(new)*
- `backend/app/services/intelligence_api_client.py` *(new)*
- `backend/app/schemas/intelligence_api.py` *(new)*
- `backend/app/routers/intelligence.py`
- `backend/app/routers/dashboard.py`
- `backend/tests/test_phase7.py` *(new)*
- `backend/docs/openapi.json`
- `PHASE7_INTELLIGENCE_API_REPORT.md` *(new)*

---

## Known Limitations (Same as Baseline)

- Local PostgreSQL is not running; Postgres-only integration tests (RLS, compliance, webhook, learning, Phase 7 API) skip/error.
- Local Redis is not running; Celery/Redis runtime validation and Pub/Sub are code-path only.
- `SENTRY_DSN` is empty in dev; production deploys must populate it.
- Full migration of all legacy routers (Money Audit, Recovery Match, Pricing, Inventory, Chat, Agent) to the Intelligence API is intentionally staged to preserve backward compatibility and avoid large rewrites in a single pass.

---

## Next Steps

1. Continue incremental application refactor:
   - Migrate `/api/v1/decisions/recommend` to consume `/intelligence/reason` when confidence is high.
   - Add Intelligence API-powered endpoints to Money Audit, Recovery Match, Pricing, and Inventory routers behind feature flags.
   - Refactor Chat/Agent feed to call `/intelligence/reason` and `/intelligence/plan` for structured responses.
2. Add load/contract tests for the new unified endpoints.
3. Run the full backend test suite after each refactor and regenerate `backend/docs/openapi.json` if endpoints change.
