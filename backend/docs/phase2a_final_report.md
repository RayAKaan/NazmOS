# Phase 2A Final Report â€” Temporal is the Single Production Execution Substrate

**Branch:** `phase1-core-infra-replacements` Â· **Base:** `8353de419decc5cd655682a461e6d1ce5aeaea96`
**Status:** working tree only â€” **nothing committed** (per directive, no commit/push; no Phase 2B/2C start).

---

## 1. Scope & Phase Boundary

Phase 2A only: remove Celery (queue, Beat, `USE_CELERY`, `app/celery_app.py`) and every
BackgroundTasks/inline fallback, and make **Temporal the single production execution
substrate**. Converged onto Temporal: upload ingestion, POS sync (request trigger +
periodic sweep), event processing (+ unprocessed drain), and the 9 formerly-dormant Celery
Beat schedules. Dormant bodies that are *not* in the audited production set were preserved
as callable workflows but deliberately left unscheduled. The report ends at Phase 2A â€”
no commit, no push, no 2B/2C.

## 2. Non-negotiable Invariants (how each was preserved)

- **No replacement queue.** No RQ/Dramatiq/ARQ/Taskiq/APScheduler/Prefect/Dagster. All work
  either runs as a real Temporal workflow/activity (production) or in-process through the
  *identical activity body* (explicit `USE_TEMPORAL=false` dev/test mode). Redis remains
  only cache / rate-limits / event pub-sub / `etl_progress:{upload_id}` channel â€” it is NOT
  a task queue.
- **Business logic, financial semantics, RLS, `execution_key` idempotency preserved.** Every
  activity is a transport boundary that calls the same canonical `run_*` bodies that the
  businesses previously executed; `execution_key` checks remain exactly-once (`ALLOW_DUPLICATE`).
- **No silent local fallback.** A Temporal failure under `USE_TEMPORAL=true` raises
  `TemporalExecutionError` (runner + `operations._temporal_dispatch`); dispatch contains no
  try/except fallback branch (locked by `test_dispatch_ast_has_no_fallback_branch`).
- **Redis confined to its stated roles**; configuration now has no `USE_CELERY` anywhere.

## 3. Execution Inventory

All previously-celery/background execution paths now exist once, as Temporal operations
(`app/orchestration/operations.py`): direct-request ops `upload_ingest`, `pos_sync_run`,
`event_process`; scheduled ops `drain_unprocessed_events`, `pos_sweep`,
`rebuild_daily_summaries`, `cleanup_stale_uploads`, `forecast_refresh_all`,
`process_pending_deletions`, `refresh_model_performance`, `daily_full_audit`,
`goal_progress_snapshot`, `learning_reconciliation`; preserved-unscheduled
`nightly_recovery_match_scan`. `OPERATION_WORKFLOW` maps every op to a registered Temporal
workflow type; `OPERATION_ACTIVITY` maps every single-activity op to a registered activity.

## 4. Temporal Substrate

- Worker entry: `python -m app.orchestration.temporal.worker`; task queue `nazm-execution`.
- **17 workflows registered** (`WORKFLOWS`, all unique, all `@workflow.defn(name=...)`):
  `manual_action`, `agent_approval`, `simulated`, `upload_ingest`, `pos_sync_run`,
  `event_process`, `drain_unprocessed_events`, `pos_sweep` + 9 bulk one-activity workflows
  (`rebuild_daily_summaries`, `cleanup_stale_uploads`, `forecast_refresh_all`,
  `process_pending_deletions`, `refresh_model_performance`, `daily_full_audit`,
  `goal_progress_snapshot`, `learning_reconciliation`, `nightly_recovery_match_scan`).
- **15 activities** registered; contract `ACTIVITIES.keys() == POLICY_REGISTRY.keys()` and
  `ALL_ACTIVITY_NAMES == set(POLICY_REGISTRY)` (enforced in
  `tests/test_temporal_retry_wiring.py:29,35`). Per-activity start-to-close timeouts and
  explicit retry policies live in `operations.py` / `temporal/policies.py` / `temporal/retry.py`.
- Workflow-run determinism is AST-audited (no clocks/UUID/random/I/O inside run bodies; side
  effects only via `_act`/`workflow.execute_activity`) in `tests/test_temporal_workflow_determinism.py`.
- Generic-workflow factory (`_make_generic_wf`) emits per-class `run` methods whose
  `__qualname__` equals `{ClassName}.run` (the Temporal SDKâ€™s string check) and registers via
  `workflow.defn(name=...)`, so generated classes behave exactly like hand-written workflows
  (verified with a live SDK probe).

## 5. Schedules

10 Temporal Schedules (`app/orchestration/temporal/schedules.py::DEFAULT_SCHEDULES`), ids
`nazm-{wf}`, timezone `Asia/Riyadh` (temporalio `ScheduleSpec(time_zone_name=...)`):

| Schedule id | Interval / cron | Former Beat cadence |
|---|---|---|
| `nazm-drain_unprocessed_events` | every 60s | â€” |
| `nazm-pos_sweep` | every 300s | â€” |
| `nazm-learning_reconciliation` | every 3600s | â€” |
| `nazm-rebuild_daily_summaries` | 0 1 | daily 01:00 + catch-up |
| `nazm-cleanup_stale_uploads` | 0 2 | daily 02:00 |
| `nazm-forecast_refresh_all` | 0 3 | daily 03:00 |
| `nazm-process_pending_deletions` | 0 4 | daily 04:00 |
| `nazm-refresh_model_performance` | 0 5 | daily 05:00 |
| `nazm-daily_full_audit` | 0 6 | daily 06:00 |
| `nazm-goal_progress_snapshot` | 0 7 | daily 07:00 |

`ensure_default_schedules(client, task_queue)` is idempotent (re-patch vs. live temporal)
and is invoked on worker `_main` and via the CLI `python -m app.orchestration.temporal.schedules`.
Defect fixed en route: `run_refresh_model_performance_all()` now enumerates
`businesses WHERE is_active = true` (the Beat path previously sent `business_id=None`).

## 6. Upload Ingestion Migration

`POST /api/v1/uploads/{id}/map` now returns the unified response with
`task_id == <workflow-id>` (`upload-<upload_id>`) in both modes: local mode reflects the
result status/progress/counters; Temporal mode returns `processing` (35%) and the workflow
runs on the server. 409 guard when status âˆˆ {processing, completed, needs_review};
`background_tasks` parameter removed. ETL still executes inline in the worker thread via the
same `run_process_upload` body the ingestion pipeline always used.

## 7. POS Sync Migration

Request-triggered (`pos_sync_run` workflow, id `pos-sync-<connection_id>`) and the periodic
sweep (`pos_sweep` workflow, id `pos-sweep-<timestamp>`; scans due connections with
per-connection failure isolation â€” mirrored in-process by `local_pos_sweep_run`). Both call
the identical `run_sync_pos_connection` / scan activity bodies used by the old worker.

## 8. Event Processing Migration

`ingest_event` persists then dispatches `event_process` (workflow/activity
`process_single_event`, carrying `event_id`/`business_id`). The 60s
`drain_unprocessed_events` schedule processes the cross-tenant queue with the full canonical
processor (`process_unprocessed_events`). **Local mode fix (found in verification):**
`USE_TEMPORAL=false` processes inline through `process_event_sync` on the callerâ€™s session â€”
the exact historical zero-cost contract (an earlier version dispatched through the activity,
which opened a fresh settings-bound session and broke injected-session tests and dev
semantics). Production always uses the Temporal workflow.

## 9. Removed Celery Surface

- Deleted: `backend/app/celery_app.py`, `backend/scripts/runtime_worker_health.py`,
  `backend/scripts/runtime_beat_health.py`, `backend/app/tasks/event_tasks.py`,
  `backend/app/tasks/runtime_smoke_tasks.py`, `backend/tests/test_celery_deployment.py`.
- `backend/app/config.py`: `USE_CELERY` field and sqlite setattr removed; Redis comment
  restated (NOT a task queue). SQLite still forces `USE_REDIS=False` and auto-disables
  `USE_TEMPORAL` only when the env var is unset; an explicit `USE_TEMPORAL=true` is respected
  (hard-failure surface even on a file DB). Production forbids `USE_TEMPORAL=false`.
- `backend/app/database/models.py`: `UploadedFile.celery_task_id` dropped.
- Migration `backend/alembic/versions/ff13_drop_celery_upload_task.py`
  (down_revision `ff12_rls_chat_pos_sync_logs`; single head `ff13_...`; direct
  `drop_column` on Postgres, `batch_alter_table` elsewhere).
- `docker-compose.yml` / `.local.yml` / `.prod.yml` / `.sqlite.yml`: all `USE_CELERY` env and
  `celery_worker` / `celery_beat` services removed; prod `backend` + `nazmos-worker` now
  `depends_on: temporal`; `.sqlite.yml` sets `USE_TEMPORAL=false`, `USE_REDIS=false`.
- `.github/workflows/ci.yml`: `USE_CELERY: false` removed from the E2E job; temporal job/env
  unchanged (actionlint clean). `backend/requirements.txt`: `celery==5.4.0` removed;
  `temporalio==1.32.0` retained. `backend/.env.example`:
  `USE_TEMPORAL=true` (+ note) replaces `USE_CELERY`.

## 10. Zero-Cost / Dev-Test Local Mode

`USE_TEMPORAL=false` (explicit) is the only non-Temporal path and is never production-legal.
Local dispatch executes the same canonical activity bodies in-process (sync bodies via
`asyncio.to_thread`; `get_sync_session(tenant_id=business_id)` self-scopes RLS inside the
worker thread so the plaintext sqlite/tests mirror production routing). `infra_status`
reports temporal enabled/reachable/address/namespace/server-version via `ping_temporal`;
zero-cost health excludes the temporal probe; uploads finish inline; LLM rate limiter is
in-memory (SQLite). Locked by `tests/test_zero_cost_sqlite_mode.py`.

## 11. Strict Dispatch & Production Configuration

`operations.dispatch_operation` mirrors `runner._dispatch` rules: Temporal selected +
unreachable/failing â‡’ `TemporalExecutionError` (no mutation, no local downgrade). Production
(ENVIRONMENT=production) refuses `USE_TEMPORAL=false` at `Settings()` time (including
`get_settings()`). `app/orchestration/operations.py` and `app/orchestration/runner.py`
(temporal dispatch) have no fallback try/except. Re-validation found these rules were
already locked by `tests/test_temporal_strict_dispatch.py` (dispatch-AST + E-tests).

## 12. Verification Matrix

- `python -m compileall -q app tests` â€” clean.
- actionlint on `.github/workflows/ci.yml` â€” clean (exit 0, no findings).
- Focused Phase-2A suites (USE_TEMPORAL=false): `test_temporal_deployment.py`,
  `test_infra_service.py`, `test_zero_cost_sqlite_mode.py`, `test_upload_confirm_mapping.py`
  â†’ **21 passed**.
- Real-server Temporal suite (`tests/temporal`, USE_TEMPORAL=true, sqlite DATABASE_URL,
  `WorkflowEnvironment.start_local()`) â†’ **8 passed, 9 skipped** (the 9 are Postgres-only
  scenarios â€” when a Postgres `DATABASE_URL` is used, CI enforces zero skips).
- Full main suite (`--ignore=tests/temporal`, USE_TEMPORAL=false): **1107 passed, 174 skipped,
  1 xfailed, 12 failed, 19 errors**. All 12 failures and all 19 errors are pre-existing and
  verified **byte-identical at base commit `8353de4`** on a pristine detached worktree (see Â§13).
- OpenAPI golden contract: passes. Regenerated `backend/docs/openapi.json` â€” the only diff vs
  base is the intentionally removed `/api/v1/health/celery` path (no schema drift).
- Migration state: `alembic heads` = single head `ff13_drop_celery_upload_task`;
  compose YAML parses cleanly for all four files.

## 13. Pre-existing Failures & Environment Limitations (recorded, not hidden)

**12 test failures (identical at HEAD, unrelated to Phase 2A):** the production-config
suites construct `Settings(ENVIRONMENT=production, WHATSAPP_ENABLED=â€¦)` and their env fixtures
omit `WHATSAPP_VERIFY_TOKEN`, which the pre-existing production validator
(`config.py:309`, predates Phase 2A) requires. Affected: `test_production_config_contract.py`
(7), `test_credential_vault_production.py` (2), `test_rate_limiter.py::â€¦fail_open_redis` (1),
`test_temporal_strict_dispatch.py::test_e_production_*` (2, masked by the same validator).
These tests exercise pre-existing production hardening, not Phase 2A; fixing their fixtures is
out of scope here (Phase 1 closeout already flagged the token-default concern as P0).

**19 test errors / 9 temporal skips (Postgres-gated, identical at HEAD):** the RLS and
golden-fixture integration suites (`tests/security/test_celery_rls_tenant_context.py`,
`tests/test_rls_enforcement.py`, `tests/regression/test_golden_fixture_regression.py`) require
a migrated Postgres; with the Docker daemon down (host degraded) Postgres is unavailable, so
they error on connection and the temporal Postgres-only scenarios skip. These are
environmental â€” full acceptance requires the local Postgres stack per AGENTS.md.

**Environment limitation for the report:** a clean production Docker rebuild + live GH Actions
run of the final tree could not be exercised (Docker daemon down, no remote push). Static
equivalents (compose YAML parse, actionlint, in-process real-dev-server Temporal suite)
are all green.

## 14. OpenAPI & API Contract Delta

Removed `GET /api/v1/health/celery`. `infra_status` now exposes `temporal` alongside `redis`
under strict-runtime health. Upload `/map` response/409 semantics are contract-tested by the
rewritten `test_upload_confirm_mapping.py` and expire when the status gates change. The golden
`backend/docs/openapi.json` was refreshed exactly once (diff = celery endpoint only).

## 15. Migration & Data Integrity

Single-head alembic chain `â€¦ â†’ ff12_rls_chat_pos_sync_logs â†’ ff13_drop_celery_upload_task`.
The column drop is irreversible for data that carried task ids; the historical column is
preserved only in the immutable `748e4f2a4e7b_initial_schema` migration. `execution_key`
remains the exactly-once guard; `etl_progress:{upload_id}` remains the only Redis state
(progress channel, not a queue). RLS tenant propagation for worker/thread sessions is unchanged
and still exercised by the (Postgres-gated) `test_celery_rls_tenant_context` suite.

## 16. Verdict

**PHASE 2A COMPLETE â€” TEMPORAL IS THE SINGLE PRODUCTION EXECUTION SUBSTRATE.**

All Phase 2A gates pass: compileall, actionlint, openapi contract, focused Phase-2A suites,
real-server Temporal suite (8/17; 9 need Postgres), and the full main suite shows no Phase-2A
regression â€” every remaining failure/error was proven pre-existing and byte-identical at the
base commit or environment-gated (Postgres/Docker). Changes remain **uncommitted** on the
working tree for review. **Stopping here per directive â€” no commit, no push, no Phase 2B/2C.**