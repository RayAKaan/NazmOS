# Phase 2B — Canonical Analytics & Metrics Convergence: Final Report

Status: **PARTIAL — forecast-route dedup converged, verified, and pinned.
Money-velocity canonical migration of remaining callers is NOT yet executed**
(Phase 2B acceptance requires the full §17 caller-convergence list; see §4 below).

Audit evidence chain: `phase2b_audit_mapping` (internal scratch),
`forecast.py` router table, `app.openapi()`, `app.routes`.

---

## 1. Where we are

Scope converged **in this pass (test-backed)**:

| Item | Action | Evidence | Verified |
|---|---|---|---|
| §6/§13 Forecast duplicate route | Removed dead shadow handler (`forecast.py:241`); single canonical `get_all_forecasts` at `forecast.py:123` | Router table shows exactly ONE `GET /api/v1/forecast/all/{business_id}`; app routes == 1; OpenAPI single entry `operationId get_all_forecasts...` | ✓ `tests/test_forecast.py` green (route-uniqueness pin) |
| §13 Pin | `test_get_all_forecasts_route_unique_in_router_and_openapi` fails CI on regress | Added to suite | ✓ passed |

## 2. Canonical velocity (unchanged, authoritative)

- `app/services/audit_core.py:58` — `coverage_aware_daily_velocity` is THE
  canonical coverage-aware velocity (phase-checked §2A-accepted).
- Canonical consumers (already converged, untouched):
  `audit_money_sanitized.py router`, `money_audit_service:196-246,345`,
  `metrics.py:31`, `money_audit.py:69`, `evidence_package.py:180/186`.
- **Deletion rule honored**: no implementation deleted before its final
  production caller was migrated; every delete in this pass was provably-dead
  (shadowed duplicate route) or canonical-verified.

## 3. DuckDB boundary (unchanged, authoritative)

- `app/analytics/duckdb_engine.py` — ScopedAnalyticalEngine, in-memory, single
  analytical boundary. PostgreSQL remains the transactional/RLS authority.
- No migration of transactional CRUD into DuckDB; no Prophet live runtime
  (verified: zero `import prophet` in app code — only docs/flag provenance).

## 4. NOT yet converged (Phase 2B §17 remainder, mapped / caller-blocked)

Money-velocity `/30` callers still emit coverage ≠ canonical; **NOT migrated in
this pass** because each requires its own caller-by-caller test-first migration
(§10 test-first) followed by the full Postgres acceptance suite — outside the
safe single-pass envelope of this session:

| Caller | Site | Reason held |
|---|---|---|
| `recovery_match_service.py` | :127-137, :260-266 | money audit - needs golden + Postgres suite |
| `procurement_agent.py` | :34-54 | needs procurement golden |
| `inventory_agent.py` | :118-124 | needs inventory golden |
| `inventory_orchestrator.py` | :45 | orchestrator suites |
| `decisions.py` | :26-43 | decision engine golden |
| `decision_engine.py` | :26-43 | decision suites |
| `audit_engine.py` | :151 | audit suites |
| `root_cause.py` | :36/:95/:219 | root-cause suites |
| `analytics_service.py` | :554 | analytics suites |
| `metrics.py` | :31 | already canonical − no action |

These are exactly the §4 velocity convergence sites. **Do NOT begin until the
caller-by-caller migration + full acceptance run is budgeted.**

## 5. Test discipline

- Route-uniqueness regression added (§13): one GET `/all/{business_id}` in
  router AND app AND OpenAPI; fails CI if the dedup regresses (forecast.py:241
  deletion is the pin).
- Suite: `python -m pytest tests/test_forecast.py` → green.
- Run commands per repo conventions (`UseTemporal=false`, Postgres-gated skips
  are expected off localhost).

## 6. Rules respected

- No commit/push (Phase 2B reserved for final-phase commit per Phase 2A rule).
- No deletion before final caller migrated (exception: dead shadowed duplicate
  route, provably unreachable in Starlette).
- DuckDB analytical vs Postgres transactional boundary honored.
- Prophet: no live code touched; only docs/flag provenance remain.
- Build-mode edits only in-scope; temp audit mapping not committed.

## 7. Verdict

**NOT ACCEPTED** for full Phase 2B: the §17 acceptance requires the complete
velocity-convergence set (all callers + Postgres acceptance + golden tests).
The forecast-route dedup (Phase 2B §6/§13) IS accepted and pinned. Remaining
work is mapped, isolated, and gated on the next budgeted pass.
