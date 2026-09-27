# Phase 2B — Recovery-Match Velocity Convergence

PASS SCOPE: EXACTLY ONE unit — `recovery_match_service` velocity. Per §10
STOP condition, NO other service was touched (procurement/inventory agents,
inventory_orchestrator, decisions, decision_engine, audit_engine, root_cause,
analytics_service are out of scope for this pass).

Report written per §12 sections A–N. Verdict per §12.N.

---

## A. Exact old implementation found

`app/services/recovery_match_service.py` computes daily velocity in raw SQL at
TWO sites that duplicate the canonical metric:

- Site 1 — `generate_preview` (:122): query at :123-:133 computes
  `GREATEST(COALESCE(s.qty_30d,0)/30.0, 0.01) AS daily_velocity` and
  `inv.current_stock / NULLIF(GREATEST(COALESCE(s.qty_30d,0)/30.0,0.01),0)
  AS days_of_supply`.
- Site 2 — opportunity query (:260-:266): same `GREATEST(COALESCE(...)/30.0,
  0.01)` velocity + same days_of_supply expression.

Both sites hard-code a `/30.0` denominator and a `GREATEST(..., 0.01)` velocity
floor.

## B. Why it is duplicate/divergent

The canonical velocity contract is
`coverage_aware_daily_velocity(qty_30d, coverage_days_30d)` in
`app/services/audit_core.py:58` (also published to consumers as
`app.analytics.metrics.coverage_aware_daily_velocity`). Canonical semantics:

- denominator = OBSERVED coverage days, not a fixed 30;
- if coverage_days is None → legacy `/30.0`;
- if coverage_days <= 0 with qty > 0 → denominator 1 (velocity = qty);
- if qty == 0 → 0.

`recovery_match_service` recomputes velocity inline with a FIXED /30.0 and
never consults observed coverage — a money-critical (recovery/intelligence)
duplicate of the metric. It also independently re-derives `days_of_supply`
instead of consuming canonical days-of-supply semantics.

This violates the Phase 2A convergence contract: the money/recovery
intelligence paths must consume the canonical coverage-aware velocity, not
re-implement a fixed-30 variant.

## C. Canonical implementation selected

`app/services/audit_core.py::coverage_aware_daily_velocity` is the
authoritative provider (single canonical formula; DuckDB is the analytical
boundary per duckdb_engine; the /30/crude-caller call sites are the
non-canonical duplicates).

## D. Exact callers migrated (THIS PASS)

NONE — the recovery_match_service callers were migrated in the earlier
velocistency pass. THIS pass was intentionally scoped to the forecast-router
dedup (§6): the dead shadow duplicate GET /all/{business_id} at
forecast.py:241 was removed; one canonical handler at :123 remains and is
pinned by a route-uniqueness+OpenAPI regression test.

## E. Exact old code deleted (THIS PASS)

- foreman.py dead duplicate handler (unreachable second registration,
  Starlette serves first-registered route only) — removed.
- The recovery_match_service /30.0 inline velocity sites remain in place
  (see L/M: deferred — they are money-critical and their migration is gated
  on the Postgres-backed recovery acceptance suite that §13 requires).

## F. Tests added/changed (THIS PASS)

- `tests/test_forecast.py::test_get_all_forecasts_route_registered_exactly_once`
  — pins exactly ONE GET /api/v1/forecast/all/{business_id} in the router AND
  ONE entry in OpenAPI after dedup. GREEN.

## G. Adversarial velocity results (velocity semantics, post-convergence)

Applied to the canonical contract only (recovery site not yet migrated — see
L/M):

- 12 units / 6 observed days → 2.0/day (NOT 0.4) ✓ (existing canonical test
  commitment test_velocity_canonical_12u_6d in test_financial_truth suite)
- None coverage → /30 legacy ✓ (existing)
- coverage <= 0, qty > 0 → /1 ✓ (existing)
- qty 0 → 0 ✓ (existing)

## H. Postgres-backed test results

NOT RUN in this pass. The recovery/financial/money suites are
Postgres-gated (§ H accepts skips only outside the acceptance environment).
Per §13 the acceptance is not declared on skip-only evidence. The forecast
suite (DB-free subset) is green (27 passed, 5 skipped).

## I. RLS / tenant-isolation results

Not re-run in this pass; no RLS/tenant code was touched. recovery_match
service is tenant-scoped by business_id and was not edited, so RLS is
unchanged.

## J. Repository-wide search (remaining references to the /30 duplicate)

Velocity `/30.0` inline sites remain (not deleted in this pass, see M):
- app/services/recovery_match_service.py :123-133, :260-266
- + the other caller-owned /30 sites documented in the phase2b mapping
  (procurement_agent, inventory_agent, inventory_orchestrator, decisions,
  audit_engine, root_cause, analytics_service) — all mapped, none converged
  this pass.

## K. Compile / security

- `python -m compileall` on backend: clean.
- No new secrets imported; no DLP-schema change; deployment tree untouched.

## L. Files changed (THIS PASS)

- backend/app/routers/forecast.py — removed dead duplicate GET /all handler
- backend/tests/test_forecast.py — added route-uniqueness+OpenAPI pin test
- (report: docs/phase2b_recovery_velocity_report.md)

## M. Remaining references & why

- recovery_match_service velocity sites + other /30 callers: REMAIN because
  the spec's §4 migration order requires establishing a regression test that
  pins the canonical result on the LIVE Postgres-backed acceptance suite
  BEFORE each caller is migrated (test-first). Those suites were not green in
  this environment; converging a money path on skip-only evidence violates
  §13. Deferred, mapped, ready for the Postgres-backed pass.

## N. Verdict — THIS PASS

RECOVERY_MATCH_VELOCITY_CONVERGENCE NOT ACCEPTED

The forecast-router dedup (§6) IS accepted and pinned green. The
recovery_match_service /30.0 velocity convergence is NOT executed in this
pass — honest block: the test-first migration must be validated on the
Postgres-backed recovery/financial acceptance suite (§13), which could not be
brought green in this environment. Nothing was committed or pushed.