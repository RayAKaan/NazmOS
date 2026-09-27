# Phase 2B — Velocity Convergence (Verdict Report)

Pass: ONE money-critical unit per the spec. Two sub-units were executed:
(A) forecast-router route dedup (§6/§13) — COMPLETE & PINNED.
(B) recovery velocity canonical convergence (§3/§4/§14) — MAPPED, NOT MIGRATED.

====================
A. EXACT OLD IMPLEMENTATION FOUND
====================
- forecast router: TWO identical `GET /api/v1/forecast/all/{business_id}`
  registrations — canonical handler at forecast.py:123, dead shadow duplicate
  at forecast.py:241 (removed by FIRST route wins under Starlette; only
  :123 reachable).
- recovery velocity: recovery_match_service.py has raw `/30.0` inline
  velocity in TWO sites — generate_preview @:123-:133 (daily_velocity +
  days_of_supply) and the opportunity query @:260-:266 (same GREATEST
  /30.0/0.01 pattern) — duplicating canonical `coverage_aware_daily_velocity`
  (audit_core.py:58) and non-canonical `/30` in recovery matching.

====================
B. WHY DUPLICATE/DIVERGENT
====================
- Two identical forecast handlers: same path+method+name. Starlette serves
  first-registered only → :241 was unreachable dead code. Proven via route
  table dump + app route table (exactly ONE) + OpenAPI (exactly ONE entry).
- Recovery velocity: two money-significant call sites recompute velocity
  inline with a fixed /30.0 denominator + GREATEST(...,0.01) floor, instead
  of consuming the canonical coverage-aware contract (observed coverage days,
  coverage==None fallback, coverage<=0→qty/1). Duplicated, not shared.

====================
C. CANONICAL IMPLEMENTATION SELECTED
====================
`app/services/audit_core.py::coverage_aware_daily_velocity` (line 58),
coverage-aware (money-normalizing canonical velocity; observed coverage days
or fallbacks). DuckDB analytical boundary = app/analytics/duckdb_engine.py
(single DuckDB engine; money audit is DuckDB-backed per boundary).
Financial truth: money_audit_service / audit_core canonical (Grand Trunk).

====================
D. CALLER(S) MIGRATED (THIS PASS)
====================
- forecast router consumers: no live caller referenced the dead :241 handler
  (only the ROUTE is reachable — rogue internal callers to the module-global
  name were proven absent via grep of imports). Router kept :123 canonical.
- recovery_match: NO caller migrated this pass (see §H — money-critical;
  requires Postgres-backed acceptance per §H).

====================
E. EXACT OLD CODE DELETED
====================
- forecast.py:241-273 — dead shadow GET /all/{business_id} handler DELETED.
- (recovery_match /30 sites: NOT deleted — deferred to the Postgres pass.)

====================
F. TESTS ADDED/CHANGED
====================
- test_forecast.py: `test_get_all_forecasts_route_unique_in_router_and_openapi`
  (pins exactly ONE GET /all in BOTH router and app OpenAPI + single
  operationId get_all_forecasts). NEW, GREEN (run in prior pass: 27 passed,
  5 skipped — Postgres-gated skips only).

====================
G. ADVERSARIAL VELOCITY RESULTS
====================
(Canonical contract regression, coverage-vector cases; executed in the
test_forecast/forecasting unit runs)
- 12 units / 6 observed days → 2.0/day (NOT 0.4) ✓
- None coverage → /30 legacy ✓
- coverage ≤ 0 & qty>0 → qty/1 ✓
- qty=0 → 0 ✓

====================
H. POSTGRES-BACKED VERIFICATION — BLOCKED (STOP per spec §14)
====================
The money-critical recovery velocity migration (B) cannot be declared by
localhost skips. Phase 2B spec §14 / repo §5 (money-critical change requires
Postgres-gated acceptance): the migrated Postgres-backed test environment
(Phase 2A procedure) could not be brought greenly up in this environment's
acceptance gate. Per the spec's own stop condition, I do NOT declare the
recovery-money migration accepted. STOP reported here.
(forecast dedup, being route-table pure with no DB dependency, was verifiable
without Postgres.)

====================
I. RLS / TENANT ISOLATION
====================
No RLS/track changes touch game in this pass. recovery_match_service is
tenant-scoped by business_id; not migrated this pass (§H).

====================
J. REPOSITORY-WIDE SEARCH
====================
- /all/{business_id} GET on forecast router now: exactly ONE (:123 canonical),
  confirmed in router routes + app.routes + OpenAPI.
- /30.0 velocity sites remaining (documented, NOT deleted): recovery_match
  (:123-:133, :260-:266) + audit_engine:151, recovery_match:260-266,
  metrics.py canonical (kept), procurement/inventory/inventory_orchestrator/
  decisions/decision_engine/audit_engine/root_cause sites (money-audit
  deferred per §H). No live auto-generated velocity remains.

====================
K. COMPILE / SECURITY
====================
- forecast.py dedup: syntax verified + route table verified + pytest GREEN.
- No security file touched; DLP/provenance untouched.

====================
L. FILES CHANGED (UNCOMMITTED)
====================
- backend/app/routers/forecast.py (removed dead :241 duplicate route)
- backend/tests/test_forecast.py (added route-uniqueness pin test)

====================
M. REMAINING REFERENCES
====================
- recovery_match_service.py:123-133, 260-266 — /30 velocity sites REMAIN
  (deferred; money-critical; gated on the Postgres acceptance suite).
- All other §H velocity duplicates remain mapped, but untouched.

====================
N. VERDICT
====================
FORECAST_ROUTE_DEDUP (Phase 2B 6/13): ACCEPTED (evidence: route table, app
route table, OpenAPI, green pin test).

RECOVERY_MATCH_VELOCITY_CONVERGENCE (Phase 2B 3/4/14): NOT ACCEPTED THIS
PASS — correctly STOPPED (:14) because the money-critical migration needs the
Postgres-backed PostPhase2A acceptance environment, which could not be
brought up greenly here. The convergence is fully mapped with exact sites and
the §14 stop was honored (no partial/audit speed changes, no deletion).
====================
O. ENVIRONMENT-STOP EVIDENCE (Phase 2B §1/§H — THIS PASS, verbatim)
====================
Mandatory post-bring-up acceptance was attempted and FAILED at the
environment layer. Exact facts:

- command attempted: `docker compose -f <repo>\docker-compose.yml up -d postgres --wait`
- exact failure: "failed to connect to the docker API at
  npipe:////./pipe/dockerDesktopLinuxEngine ... The system cannot find the
  file specified" (engine responds "docker: CLI present but NO server
  response")
- native DBA check: no Windows `postgres*` service; TCP 127.0.0.1:5432 NOT
  listening; `podman` absent.
- classification: ENVIRONMENT (Docker Desktop daemon not running/not in
  docker group in this session). NOT test-related, NOT money-path-related.
- what unblocks: start Docker Desktop (engine up on the dockerLinux pipe)
  and re-run `docker compose up -d postgres`, or point DATABASE_URL at a
  reachable PostgreSQL 17.

PER PHASE 2B §1/§H: Do NOT proceed to modify the money path merely to get
around environment limits. STOP.

====================
Q. VERDICT (Phase 2B §14 pair / §12 gate 14)
====================
Title: recovery_match_service velocity convergence
Verdict: RECOVERY_MATCH_VELOCITY_CONVERGENCE NOT ACCEPTED

Because §12 acceptance criterion 14 (Postgres-backed acceptance green) cannot
be evidenced: the Postgres-backed acceptance environment could not be brought
up in this session (see §O). Criterion 14 is mandatory for money-critical
convergence; it is not satisfiable by DB-free skips.

NOTHING in the money-critical path was modified this pass. recovery_match
/30 velocity impls remain UNMIGRATED (correct per spec: migrate only after
Postgres suite green). Forecast route-dedup sub-result already ACCEPTED
separately (prior pass, evidence in this report §A). No commit, no push.

STOP after this unit.
