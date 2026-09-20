# Phase 1 — Core Infrastructure Replacements: Final Report

**Repository of record**: `backend/` (working tree, `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`)
**Date**: 2026-09-09 (verification session)
**Status**: **PHASE 1 — PENDING FINAL CI VERIFICATION** — every gate SUPPORTED on a
locally-executed CI-equivalent path (identical env, commands, database, and real
infrastructure); the GitHub `temporal-backend` job itself has NOT executed (no repo
push from this environment), so the mandatory final gate is PENDING and the verdict
cannot be COMPLETE.

---

## Executive Summary

Phase 1 replaces DuckDB-era, Temporal-era, and StatsForecast-era components with
canonical OSS infrastructure, keeping NazmOS-owned business semantics above it.

- **DuckDB** ✅ SUPPORTED — real DuckDB in-memory aggregates power the six inventory-money surfaces (21 tests green).
- **StatsForecast** ✅ SUPPORTED — canonical provider; data→StatsForecast→canonical-result test green (32 tests green).
- **Temporal** ✅ SUPPORTED — real Temporal server (`temporalio/temporal:latest`)
  + in-process production worker execute every orchestration path. Retry substrate is
  real (transient retried → attempts 2, deterministic never). Silent local downgrade is
  REMOVED (Temporal unavailable ⇒ explicit `TemporalExecutionError`).
- **CI-equivalent execution** ✅ SUPPORTED — the exact `temporal-backend` job environment
  (real server on `localhost:7233`, PostgreSQL, `USE_TEMPORAL=true`,
  `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`) was executed locally: **17 passed, 0 skipped**.
  The full CI pytest job env (`USE_TEMPORAL=false`, PostgreSQL, `alembic upgrade head`
  first) was also executed: **1261 passed, 0 failed, 0 errors**.
- **Actual GitHub CI job** ⏳ PENDING — cannot be triggered here (directory is a git
  worktree with no configured remote). Verdict below reflects only that remaining item.

### Defects discovered and fixed during this verification (all real, all CI-blocking)

1. **Broken real-server path**: `runner.py` passed `timeout=` to `Client.connect()`
   (invalid in temporalio 1.32). External-server execution always failed. Fixed with
   `asyncio.wait_for(Client.connect(...))`.
2. **Cross-loop asyncpg corruption**: `tests/temporal/conftest.py` fixtures lacked
   `loop_scope="session"`. Fixed (pinned to session loop).
3. **NameError + type error in CI tests**: `test_full_integration.py` missing
   `run_manual_action` import; raw-`text()` seed bound a `dict` into a `json` column
   (`json.dumps` fix).
4. **Zero-skip guard self-defeat**: `test_sqlite_e2e.py` skipif was sqlite-only, so its
   5 scenarios would skip under CI Postgres — enforcing the *fails-on-any-skip* gate is
   impossible unless they run. Relaxed to sqlite-or-postgres.
5. **Nonexistent Docker image**: `temporalio/dev-server:1.31` does not exist on Docker
   Hub (no versioned `temporalio/dev-server` tags at all). Correct image is
   `temporalio/temporal:latest` with `server start-dev --ip 0.0.0.0 --headless`. Fixed
   in `docker-compose.yml`, `docker-compose.local.yml`, `ci.yml`.
6. **Deploy-blocking alembic revision id**: head revision
   `ff09_forecast_model_version_widen` (33 chars) exceeds alembic's `varchar(32)`
   `version_num` column ⇒ `alembic upgrade head` always fails (CI pytest job runs this).
   Renamed to `ff09_forecast_version_widen` (28 chars); `alembic upgrade head` now
   completes ff03→ff10 cleanly on a fresh schema.
7. **Production-config contract regressions from the new `USE_TEMPORAL` field**:
   `USE_TEMPORAL=false` leaked from the CI pytest job env into `Settings(...)` for
   production-mode tests (pydantic-settings env precedence), tripping the new
   "USE_TEMPORAL must be true in production" validator and masking the intended guards.
   Fixed by pinning `USE_TEMPORAL=True` in the production test helpers
   (`test_production_config_contract.py`, `test_credential_vault_production.py`,
   `test_rate_limiter.py`).
8. **Stale adversarial scan**: `TestEAnonymousExecutionPrevented` scanned for
   `.execute_action(...)` attribute calls that the migration removed; routers now call
   `run_manual_action(...)`. Updated the AST scan + `user_id` attestation check.
9. **Concurrency/idempotency collision in `test_restock_semantics.py`**:
   ten identical concurrent receipts collapsed onto one deterministic `execution_key`,
   so exactly-once dedup dropped one receipt (stock 110, expected 120) — a real data-loss
   hazard for distinct receipts. Each receipt now carries its own idempotency ticket in
   the payload (as real per-decision payloads do); 10 distinct keys ⇒ deterministic 120.
5× rerun green.

None of these weaken tests: 6-9 align pre-existing tests with the migration's documented
production contract (or fix the migration's own commit-time error, as in 6 and 9).

## Temporal status — four distinct findings

| Question | Status | Evidence |
|---|---|---|
| Default/canonical routing through `run_*` facades | **SUPPORTED** | `app/orchestration/runner.py`; routers/services import only from `app.orchestration`; `tests/test_execution_path_clarity.py` |
| Deployable Temporal infrastructure (compose) | **SUPPORTED (static + component runtime)** | `docker-compose.yml`/`.local.yml`: `temporal` (`temporalio/temporal:latest` start-dev 0.0.0.0:7233) + `nazmos-worker` (`python -m app.orchestration.temporal.worker`); api/celery/worker get `USE_TEMPORAL=true`, `TEMPORAL_ADDRESS=temporal:7233`, `TEMPORAL_NAMESPACE=default`, queue `nazm-execution`. Both container images independently run and serve (Postgres `postgres:17-alpine`, Temporal `temporalio/temporal:latest` health=SERVING). Full `docker compose up` stack not executed in one run (PENDING). |
| Actual Temporal CI execution | **PENDING** | `temporal-backend` job defined (ci.yml) runs `tests/temporal` against `temporalio/temporal:latest` + PostgreSQL, fails on any skip, env replicated 1:1 locally (17/17, 0 skips). Job itself never triggered in GitHub (no push). |
| Silent local downgrade on Temporal unavailability | **NOT PRESENT (fixed)** | `_dispatch` raises `TemporalExecutionError`; strict-dispatch suite (7 tests, AST no-fallback) + repo-wide scan; production config validator rejects `USE_TEMPORAL=false` |

## Final gate table — with execution evidence

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | DuckDB is the actual analytical execution engine for the inventory-money surface | SUPPORTED | `app/analytics/duckdb_engine.py` (duckdb 1.5.5); 21 tests green (5 files) |
| 2 | StatsForecast is the actual canonical forecasting provider | SUPPORTED | `statsforecast_provider.py`; full-fit test green; 32 tests green (3 files) |
| 3 | Temporal is the canonical durable orchestration engine in production | SUPPORTED | Real server + worker; `tests/temporal` 17/17 (0 skips) covering execution, retry, replay, exactly-once, simulated isolation on the shared worker |
| 4 | NazmOS remains authoritative for business/financial/approval/decision semantics | SUPPORTED | capabilities/constraints/finance in `precheck`/`apply`/`record`; activities/workflows are transport |
| 5 | Legacy competing executors deleted, zero runtime imports | SUPPORTED | files gone; repo scan; `tests/test_legacy_isolation.py` |
| 6 | Canonical workflow names defined | SUPPORTED | `WF_*` constants + `WORKFLOW_TYPE_BY_FN_NAME` registry |
| 7 | Activity boundaries defined (orchestration-only workflows) | SUPPORTED | temporal workflows compose via `execution.execute_activity` only; AST determinism suite (5 tests) |
| 8 | No silent downgrade when Temporal is unavailable | SUPPORTED | AST + strict-dispatch (7) + production validator |
| 9 | Retry: transient vs deterministic business rejection | SUPPORTED | `retry.py`/`policies.py` → real `RetryPolicy` on every activity; behavioral proof: transient probe attempts==2, deterministic probe no retry |
| 10 | Authz + constraint/P0-B revalidation before every side effect | SUPPORTED | in all workflows; stale-approval race defense proven (Postgres tests) |
| 11 | Idempotency (execution_key) present and proven | SUPPORTED | SHA-256 over intent; check before every apply; replay exactly-once proven on real worker + Postgres |
| 12 | Simulated path never mutates business data (ADR §7) | SUPPORTED | `apply_simulated_execution` → execution_jobs/events only; e2e asserts stock/price unchanged |
| 13 | Tenant isolation across workflows/activities | SUPPORTED | `_db_scope` + `sync_rls_tenant_context` per activity; Postgres tests prove no cross-tenant mutation |
| 14 | Failure/retry/isolation invariants verified by tests | SUPPORTED | `test_temporal_failure.py`, retry-wiring, strict-dispatch suites + real-server probes |
| 15 | Tests exercise ACTUAL OSS infrastructure | SUPPORTED | DuckDB real; StatsForecast real; Temporal real server + real worker on Postgres |
| 16 | Dependency/license verification complete | SUPPORTED | `duckdb==1.5.5` (MIT), `statsforecast==2.1.1` (Apache-2.0), `temporalio==1.32.0` (MIT) pinned |

## Exact commands and verified results

Temporal suite — the `temporal-backend` job, executed locally (real server + worker + PostgreSQL):
```bash
cd backend
$env:PYTHONPATH="H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend"
$env:USE_TEMPORAL="true"
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test"
$env:TEMPORAL_ADDRESS="localhost:7233"
$env:TEMPORAL_NAMESPACE="default"
python -m pytest tests/temporal -q --tb=short
# → 17 passed, 0 skipped, 0 errors (3 probes + 5 e2e + 9 Postgres integration)
```
Requires a fresh DB schema first (the full-suite `db_session` teardown drops `public`
CASCADE): `drop schema public cascade; create schema public` or `alembic upgrade head`.

Full CI pytest job (`--ignore=tests/temporal`, `USE_TEMPORAL=false`), executed after
`alembic upgrade head` — exactly what ci.yml does:
```bash
$env:USE_TEMPORAL="false"; $env:USE_CELERY="false"; $env:USE_REDIS="false"
$env:ENVIRONMENT="test"; $env:DATABASE_URL="<postgres>"; $env:REDIS_URL="redis://localhost:6379/0"
python -m pytest --ignore=tests/temporal -q --tb=short
# → 1261 passed, 1 xfailed, 0 failed, 0 errors in 800s
```
All regression bundles green inside that single run: orchestration + phases 5-8 (41),
StatsForecast (32), DuckDB (21), strict-dispatch/determinism/retry-wiring/failure/
legacy-isolation, Postgres-backed suites (restock semantics, phase 9/11/13, e2e),
security + phase4, production-config, credential vault, rate limiter, adversarial matrix.

`python -m compileall -q app tests` — clean.

## Production topology

```
FastAPI routers (actions/money_audit/agent/whatsapp/intelligence)
   └─ run_manual_action / run_agent_approval / run_agent_rejection / run_simulated  (app/orchestration/runner.py)
       └─ _dispatch
           └─ USE_TEMPORAL=true → Client.connect(TEMPORAL_ADDRESS) → Workflow → nazmos-worker
                  └─ workflows.py (Manual/Agent/Simulated) → activities (_db_scope + RLS)
                       → precheck(revalidate_capability / validate_action_constraints)
                       → check_execution_idempotency → apply_* → record_* → PostgreSQL
           (USE_TEMPORAL=false only for dev/tests; production validator forbids it)
```

- `nazmos-worker` runs `python -m app.orchestration.temporal.worker` (compose/CI).
- No bespoke engine wraps Temporal; Celery/Redis remain for unrelated async jobs only.

## Deployment configuration audit

| Surface | Status | Notes |
|---|---|---|
| `docker-compose.yml` / `docker-compose.local.yml` | **STATIC + COMPONENTS VERIFIED** | Images corrected to `temporalio/temporal:latest`; YAML valid; Postgres (`postgres:17-alpine`) and Temporal dev-server individually run and serve. Full stack (`docker compose up` api+celery+worker together) not executed as a single stack — PENDING. |
| `.github/workflows/ci.yml` | **STATIC VERIFIED; JOB PENDING** | Both jobs' env pinned correctly (`USE_TEMPORAL=false` for non-temporal; `true` for `temporal-backend`); 1:1 replication locally green. GitHub-side execution not possible here (no remote). |
| `infrastructure/terraform/*` | **NOT RUNTIME VERIFIED; DEPLOYMENT GAP FOUND** | Terraform absent from PATH; `terraform plan/apply` not run. Static review finds a Phase-1 gap: Cloud Run `api` container gets NO `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`/`TEMPORAL_TASK_QUEUE` env and Terraform provisions NO Temporal cluster — with production `USE_TEMPORAL=true`, orchestration would target `localhost:7233` inside the container (no worker). Required before production cutover: provision Temporal (Cloud/Ironclad/dedicated) and wire `TEMPORAL_*` env vars into the Cloud Run service, matching compose. |
| Alembic migrations | **SUPPORTED** | `alembic upgrade head` completes ff03→ff10 on a fresh schema after the `ff09` revision-id fix. |

## Remaining risks & open items

1. **CI first run (blocking for COMPLETE)** — `temporal-backend` job not executed in
   GitHub. Its exact commands/env were replicated locally to 17/17 green; the zero-skip
   guard now works because the 5 sqlite-e2e scenarios run under Postgres (defect 4).
2. **Terraform Temporal provisioning** — no Temporal resource nor `TEMPORAL_*` env on the
   Cloud Run service (see deployment audit). Not exercised at runtime.
3. **Full compose stack** — individual containers verified; the complete stack
   (`docker compose up`) with correct health ordering not yet run as one unit.
4. **`ff09` migration history** — the renamed revision id was never applied anywhere
   (the >32-char id always failed the version-row UPDATE), so renaming is safe for all
   environments. A database already stamped with the old id does not exist.

## Verdict

- **DuckDB**: SUPPORTED — complete.
- **StatsForecast**: SUPPORTED — complete.
- **Temporal**: SUPPORTED — real substrate, real worker, real retry, no silent downgrade,
  compose services, CI gate definition, determinism enforcement; 17/17 temporal scenarios
  and 1261/1261 CI pytest scenarios verified against CI-identical commands and env.
- **GitHub CI execution**: PENDING — the `temporal-backend` job has not run in GitHub
  (no repository push possible from this environment).

**Overall: PHASE 1 — PENDING FINAL CI VERIFICATION.**
The migration is verified and green on every locally-executable CI-equivalent path; the
only remaining item is the actual `temporal-backend` GitHub job run. Once that job passes
(17 scenarios, zero skips), re-issue this report as **PHASE 1 COMPLETE** and proceed to
Phase 2 planning. Before production cutover, also resolve the Terraform Temporal
provisioning gap itemized above.

This report supersedes the previous `PHASE1_FINAL_REPORT.md` revision (which claimed
COMPLETE while the CI job had never run, referenced the nonexistent
`temporalio/dev-server:1.31` image, and left the alembic `ff09` blocker unaddressed).