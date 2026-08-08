# Phase 4 — Decision & Explainability Engine Report

**Date:** 2026-08-06
**Branch:** main
**Baseline:** Phases 0–3 completed and green.

## Summary

Implemented the Decision & Explainability Engine. It generates ranked,
auditable decisions by combining rule-based guards with signals from business
memory, the knowledge graph, external context, and recent events. Every
decision is stored with full evidence, alternative actions, and a human-
readable explanation. No ML/RL is hardcoded; scoring is deterministic and
transparent.

## What was built

### Data model (`backend/app/database/models.py`)

- `IntelligenceDecision` — full decision record:
  - `decision_type`, `input_event_ids`, `rules_applied`
  - `memory_snapshot`, `graph_evidence`, `context_evidence`
  - `candidate_actions`, `ranked_action`
  - `confidence`, `expected_roi`, `risk_score`, `urgency`
  - `status`, `approved_by`, `approved_at`
  - `explanation` (structured JSON)
- `DecisionStatus` enum (`draft`, `approved`, `rejected`, `executed`).

### Schemas (`backend/app/schemas/decision.py`)

- `CandidateAction`, `DecisionGenerateRequest`, `DecisionOut`
- `DecisionExplainOut`, `DecisionApprovalRequest`

### Service (`backend/app/services/decision_engine.py`)

- Preserved the existing synchronous `DecisionEngine` class used by
  `app/routers/decisions.py`, `app/routers/chat.py`, and `tests/test_etl_pipeline.py`.
- Added new Phase 4 async functions:
  - `generate_decision` — gathers memory/graph/context/event signals and
    produces a ranked decision.
  - `get_decision` — fetch by id.
  - `explain_decision` — build human-readable explanation with evidence and
    alternatives.
- Candidate action generators:
  - `restock` from low-stock / reorder-flag memory.
  - `pricing_increase` / `pricing_decrease` from price history and top-product
    velocity.
  - `discount` from repeated price drops (dead-stock signal).
  - `supplier_switch` from weak `SUPPLIES` graph relationships.
- Scoring function weights: ROI 35%, confidence 25%, urgency 25%, risk -15%,
  with context adjustments for holidays and inflation.

### Router (`backend/app/routers/intelligence.py`)

- `POST /api/v1/intelligence/decisions/generate`
- `GET /api/v1/intelligence/decisions/{decision_id}`
- `GET /api/v1/intelligence/decisions/{decision_id}/explain`

### Migration

- `backend/alembic/versions/7a38b41efb11_add_intelligence_decisions_table.py`
  - Creates `intelligence_decisions`
  - Adds RLS tenant-isolation policy
  - Grants `nazmos_app` role CRUD privileges
  - Linear history: head after `357f3cbca428`

### Tests

- `backend/tests/test_decision_engine.py`
  - SQLite-backed generation tests for restock, pricing, and supplier signals.
  - Explanation and retrieval tests.
  - Postgres-only API integration tests (skipped locally).

### OpenAPI contract

- `backend/docs/openapi.json` regenerated with the three new decision
  endpoints and `Decision*` schemas.

## Verification

```text
cd /home/user/NazmOS/backend && pytest -q
223 passed, 56 skipped, 28 warnings, 2 errors in 7.89s
```

- The 2 errors are the known environmental Postgres/RLS failures
  (`tests/test_rls_enforcement.py`) because PostgreSQL is not running locally.
- The 56 skipped tests include Postgres-only integration tests from Phases 0–4.
- Backend boots in SQLite dev mode; `/health` returns 200.
- Alembic head is `7a38b41efb11`; history is linear.
- Workspace cleaned of `__pycache__`, `.pyc`, `.pytest_cache`, DB files, and
  empty upload dirs.

## Not solved / Next steps

- Postgres-only integration tests require a running local PostgreSQL instance.
- Redis Pub/Sub and Celery runtime paths are code-verified only (no local Redis).
- Phase 5: Agents, Planning, Simulation, Execution engines (`plans`,
  `simulations`, `execution_jobs`, specialized agents).
