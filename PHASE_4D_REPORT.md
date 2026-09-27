# PHASE 4D — Temporal Durable Dispatch & Recovery for the Business Loop

**Status: DONE [V]** — 21-stage `CycleRun` dispatched over Temporal via three
activities + `CycleRunWorkflow`; crash-resume, reconcile-before-retry, and
budget semantics proven by the new real-server suite; full regression green;
live `temporal-1` + rebuilt `nazmos-worker-1` running and polling
`nazm-execution`.

## Result (TL;DR)

The Business Improvement Loop is now a durable Temporal workflow. A single
`business_cycle_run` workflow orchestrates `business_cycle_start` →
`business_cycle_advance` (≤ `BUSINESS_CYCLE_MAX_ADVANCES`, from
`operations.py`), with `business_cycle_reconcile` as the reconcile-before-retry
gate. Worker restart resumes the run mid-cycle from the persisted
`cycle_runs` snapshot (lossless `CycleRun.serialize()` seam from 4A/4B), the
advance budget is honored with no blind retries, and reconcile requeues only
while the cycle is still within budget. Also closed three pre-existing
full-regression gaps this phase surfaced: an AsyncRun advisor deadlock
(`synthetic_mocked_advisor` made async), scanner-invisible RLS coverage for the
`cycle_runs` table, and a stale OpenAPI golden (loop-console routes).

## Deliverables

| Artifact | Source | Evidence |
|---|---|---|
| `tests/temporal/test_cycle_run_workflow.py` (new) | `backend` | 6/6 passed (real dev server + production-ish worker) |
| `business_cycle_start/advance/reconcile` activities | `app/orchestration/temporal/activities.py` | registered + wired in `tests/test_temporal_retry_wiring.py` |
| `CycleRunWorkflow` (`business_cycle_run`) | `app/orchestration/temporal/workflows.py` | registered in `tests/test_temporal_workflow_determinism.py` (updated) |
| `local_business_cycle_run` + OP/WF consts + timeouts | `app/orchestration/operations.py` | compileall + suite |
| 3 TRANSIENT retry policies | `app/orchestration/retry.py` | wiring invariant `ACTIVITIES.keys() == POLICY_REGISTRY.keys() == ALL_ACTIVITY_NAMES` |
| `synthetic_mocked_advisor` → `async def` (fix) | `app/services/business_loop/policy_registry.py` | `'dict' object can't be awaited` eliminated (ADVISORY stage index 8) |
| `tests/temporal/conftest.py` `schema_ready` public-schema fix | `backend` | `InvalidSchemaNameError` eliminated on Postgres |
| `ff15_cycle_runs_rls_coverage` migration (new) | `alembic/versions/` | RLS suite green; scratch-DB chain apply verified policy at rest |
| `docs/openapi.json` regenerated (stale golden) | `backend` | `UPDATE_GOLDEN=1` then contract test green |
| `PHASE_4D_REPORT.md` + `MIGRATION_MATRIX.md` §11 4D row | repo root | — |

## Workflow semantics (final)

1. **Start**: `business_cycle_start` under `_db_scope(business_id)`. Existing
   `cycle_runs` row (completed or not) → `_cycle_cursor(existing, duplicate=True)`
   and the workflow returns `done:True` (duplicate-trigger suppression). No row →
   `orch.start()` → `duplicate=False, phase4d_started=True` (idempotent start).
2. **Advance loop** (`business_cycle_advance`, ≤ 128 iterations): `_db_scope`
   → `repo.load` → rehydrate `run._snapshot` from
   `state_output["state"]` via `BusinessStateSnapshot.from_dict` → rebuild loop
   evidence via `_rebuild_evidence` → `resolve_cycle_policy(name)` → ONE
   `run_one_stage(run)` → `_cycle_cursor(…, advanced, done, blocked)`. The
   Single-Task-Quality guard (defaults `max_retries_per_stage=2`,
   `stale_max_age_days=7`, `max_opportunities_per_cycle=20`) is enforced by the
   policy, and each gold-card gets at most one stage call.
3. **Reconcile-before-retry** (`business_cycle_reconcile`): on any advance
   exception the workflow reconciles FIRST, retrying only when
   `allow_retry=True`; a `running` cycle within budget is requeued
   (`reconcile_requeued`, pending, `allow_retry=True`), at budget it becomes
   `failed` with `unknown_external_outcome_incomplete` + `allow_retry=False`,
   `failed` stages retry up to `max_retries_per_stage`, and `completed` / `ok`
   stages are never retried.
4. **Blocked tail**: budget exhausted or end-of-loop → `done`/`blocked` with the
   reconciled payload + `cycle_guard_exceeded`, never a blind retry.

## Evidence

```
# new 4D acceptance suite (real Temporal dev server + production-ish worker, Postgres)
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
$env:TEST_DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
$env:USE_TEMPORAL="true"
python -m pytest tests/temporal -q
=> 23 passed   (6 new 4D + 17 pre-existing; none skipped on Postgres)

# DB-free wiring + loop + slice regression
$env:USE_TEMPORAL="false"
python -m pytest tests/test_temporal_retry_wiring.py tests/test_business_loop_modules.py \
  tests/test_phase3_synthetic_vertical_slice.py -q
=> 68 passed

# Postgres-backed repository + console
python -m pytest tests/test_cycle_run_repository.py tests/test_loop_console.py -q
=> 14 passed

# determinism + retry wiring
python -m pytest tests/test_temporal_workflow_determinism.py tests/test_temporal_retry_wiring.py -q
=> 44 passed

# RLS coverage + predicate indexes (after adding cc15 + TENANT_TABLES registration)
python -m pytest tests/test_rls_coverage_complete.py tests/test_rls_predicate_indexes.py -q
=> 47 passed

# OpenAPI contract (golden regenerated, then checked read-only)
python -m pytest tests/test_openapi_contract.py -q
=> 1 passed

# FULL non-temporal regression (Postgres env; --ignore=tests/temporal + the two
# pre-existing broken probe files test_n2*_probe_*: 'fixture sqlite_db' missing)
python -m pytest tests -q --ignore=tests/temporal \
  --ignore=tests/test_n2_probe_inventory_emission_real.py \
  --ignore=tests/test_n2c_probe_full_json.py -p no:cacheprovider
=> 1445 passed, 1 xfailed, 0 failed

python -m compileall -q app tests alembic  => OK

# migration chain apply on fresh scratch DB (validated policy at rest, then dropped)
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_scratch"
python -m alembic upgrade head => ... ff14_cycle_runs -> ff15_cycle_runs_rls_coverage (head)
```

## Notes / limitations

- **[I] Live containers now run 4D code**: the `nazmos-worker` image predated
  4D, so it was rebuilt from current `backend/` (registered `CycleRunWorkflow` +
  `business_cycle_*` activities confirmed on-disk) and recreated via a
  **targeted** override `docker-compose.worker-fix.yml` that corrects ONLY
  `DATABASE_URL` (`nazmos_v5_dev` — the actual password the live Postgres
  authenticates with; the base compose still carried the stale `nazmos_dev`).
  The full `docker-compose.local.yml` was NOT merged because it relocates the
  worker onto `nazmos_default_net`/different volumes than the live stack.
  `nazmos_latest_merged-postgres-1`, `-temporal-1`, `-redis-1`,
  `-nazmos-worker-1` are all up; the worker polls `nazm-execution` (workflow +
  activity task queues) per `tctl taskqueue describe`.
- **[I] Temporal container shows "unhealthy"** even though the server is fully
  functional — its healthcheck probes `/dev/tcp/127.0.0.1/7233` loopback while
  the server binds `172.31.0.x:7233`. Pre-existing; worker depends on
  `service_started` so polling is unaffected.
- **[X] No live end-to-end cycle was run against the containers** — 4D
  acceptance is the real-server in-process suite above. Live-cycle
  crash-resume acceptance remains the documented 4I increment.
- **RLS + golden fixes are pre-existing-gap closures**, required because the
  full `tests` regression is the 4D gate: `cycle_runs` had a correct policy but
  invisible to the AST-based RLS coverage scanner (ff14 wrote raw SQL);
  `docs/openapi.json` predated the intentional `loop-console` routes. Both are
  scanner/golden-sync changes only — no runtime behavior change.
- **No commits/pushes; no destructive infra.** Only the worker container was
  recreated (user-approved). Dev/production DBs untouched. The two
  `test_n2*_probe_*` SQLite-fixture errors are pre-existing, unrelated, and
  excluded via `--ignore`.

## Next (4E+)

Proceed to 4E revalidation, then linked deliverables (OutcomeLedger V1 linkage,
read-only console hardening, crash-resume acceptance 4I).