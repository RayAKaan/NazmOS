# PHASE_4B_REPORT — Durable `CycleRun` Persistence (Business Loop Runtime)

Date: 2026-09-24
Prev dependency: `PHASE_4A_RUNTIME_CONTRACT_REPORT.md` (frozen contract)
Next: `PHASE_4C_REPORT.md` — Jev-native typed advisory via the canonical gateway

---

## 1. Result (TL;DR)

The Business Improvement Loop's run state is now **durable and lossless**:

- New `cycle_runs` table (migration `ff14_cycle_runs`, current alembic head) plus
  `CycleRunModel` mapping.
- The DB-free `CycleRepository` seam converted to **async**, with a real
  Postgres adapter (`PostgresCycleRepository`) implementing the durability
  contract from 4A.
- 7-test Postgres-backed suite **passes** (21.7 s), plus the Phase 3 synthetic
  vertical slice still passes (async-seam regressions checked).
- Full alembic chain through `ff14_cycle_runs` applied to a **scratch Postgres
  database** and verified at rest (table shape, indexes, constraints, FK, RLS
  policy + toggle, alembic head), then the scratch DB was dropped. [V]

---

## 2. Deliverables

| Artifact | Path | Status |
|---|---|---|
| Migration `ff14_cycle_runs` | `backend/alembic/versions/ff14_cycle_runs.py` | [V] applied + verified |
| `CycleRunModel` | `backend/app/database/models.py` (~L2030) | [V] compiles + maps |
| Async seam | `backend/app/services/business_loop/cycle.py` | [V] compiles + slice green |
| `PostgresCycleRepository` + `CycleRunConflictError` | `backend/app/services/cycle_run_repository.py` | [V] 7/7 tests |
| 4B test suite | `backend/tests/test_cycle_run_repository.py` | [V] 7 passed |
| Report | `PHASE_4B_REPORT.md` | this file |

No production behavior changed beyond making the seam async; the in-memory
repository retains identical semantics (keyed by `(business_id, cycle_id)`).

---

## 3. Why the seam went async

The `CycleOrchestrator` already drives `await`-based stages and the
`InMemoryCycleRepository` was sync-only. A durable Postgres adapter requires
`AsyncSession` (project-wide async stack: `asyncpg`, `async_sessionmaker`),
so the seam's `save()/load()` became `async def` and
`CycleOrchestrator.start()/load()` became async too. Five call sites in
`tests/test_phase3_synthetic_vertical_slice.py` were updated to `await`.
The slice (4/4) re-passes, confirming no loop-semantics regression.

Type change (`CycleRepository` — `load`):
- before: `load(cycle_id)`
- after: `load(business_id: str, cycle_id: str)` — explicit tenant scoping so an
  adapter can always filter by `business_id` (defense-in-depth under RLS).

---

## 4. Migration `ff14_cycle_runs` — what was added

- Table `public.cycle_runs`:
  - `id` uuid PK (CASCADE-less; app-generated)
  - `business_id` uuid FK → `businesses(id)` **ON DELETE CASCADE**
  - `cycle_id` varchar(64) — the idempotency key (`derive_cycle_id`, SHA-256)
  - `tenant_id`, `trigger`, `trigger_token`, `created_at`, `starting_state_version`,
    `evidence_watermark`
  - `stage_index int NOT NULL DEFAULT 0` — resume cursor
  - `completed bool NOT NULL DEFAULT false`
  - `last_error text NOT NULL DEFAULT ''`
  - `state_output json NOT NULL DEFAULT '{}'`, `stages json NOT NULL DEFAULT '[]'`
  - `schema_version varchar(16) NOT NULL DEFAULT 'loop-v1'`
  - `version int NOT NULL DEFAULT 1` — optimistic-concurrency guard
  - `updated_at timestamptz NOT NULL DEFAULT now()`
- Constraints/indexes:
  - `uq_cycle_runs_business_cycle` UNIQUE (`business_id`, `cycle_id`) — the
    idempotency guarantee at rest
  - `idx_cycle_runs_tenant_lookup` (`business_id`, `created_at` DESC) — console
    listing shape (4G)
  - `ck_cycle_runs_stage_index_nonneg` CHECK (`stage_index >= 0`)
- RLS (production tenant isolation, defense-in-depth):
  - `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
  - policy `cycle_runs_tenant_isolation` USING/WITH CHECK
    `business_id = app.current_tenant_id()`
  - `GRANT SELECT/INSERT/UPDATE/DELETE` to `nazmos_app` (guarded DO-block so the
    migration is re-runnable headless)
- `downgrade()` drops table/policy/index/constraint in correct order.

Chain: `ff13_drop_celery_upload_task` → `ff14_cycle_runs`. Verified
`python -m alembic heads` → **single head `ff14_cycle_runs`**.

**Verification gap closed:** ran the ENTIRE chain on a scratch database
(`nazmos_migrate_check`, dropped after inspection):
`\d cycle_runs`, `pg_tables.rowsecurity=t`, `pg_policy` row present,
`alembic_version=ff14_cycle_runs`. No destructive action touched the real dev DB. [V]

---

## 5. `PostgresCycleRepository` — durability contract (4A §6)

Implemented in `backend/app/services/cycle_run_repository.py`. Contract lines:

1. **Lossless round-trip.** `save()` writes the full `serialize()` surface
   (all 21 `CycleStageState`s, cursor, output, trigger, watermark, versions);
   `load()`/`all()` rehydrate via `_model_to_run()` into an identical `CycleRun`
   (`_version` restored). Test: `test_save_load_roundtrip_is_lossless`.
2. **Idempotent create on `(business_id, cycle_id)`.** INSERT uses
   `pg_insert(...).on_conflict_do_nothing(index_elements=[...])` on Postgres
   (unique constraint backs it at rest); a raced duplicate never becomes a
   second row. Test: `test_duplicate_create_is_idempotent` (COUNT == 1).
3. **Tenant scoped.** `load` and `all` filter by `business_id` explicitly;
   RLS stands behind it. Test: `test_load_is_tenant_scoped`.
4. **Optimistic concurrency.** UPDATE predicates on `version = run._version`;
   rowcount == 0 ⇒ rollback + `CycleRunConflictError` (no silent clobber).
   Test: `test_stale_version_conflict` (two real sessions, both read vN, A wins,
   B raises).
5. **Terminal protection.** Completed rows are immutable; a later mutation
   raises `CycleRunConflictError`, a re-save of the identical completed run is a
   no-op returning the pinned version. Test: `test_completed_run_is_immutable`.
6. **Listing shape.** `all(business_id)` ordered `created_at DESC`. Test:
   `test_all_lists_tenant_scoped_newest_first`.
7. **Orchestrator proves it.** `test_orchestrator_persists_full_cycle` drives
   the REAL 21-stage orchestrator through the durable repo (evidence → advisory
   (mocked jev) → governance → execution → summary) and asserts the persisted
   terminal shape.

### Terminal-shape fact (documented, tested)

`_stage_summary` (stage index 19 in `CycleStage.ordered()`) sets
`run.completed = True` and advances the cursor to 20; `run_one_stage`
short-circuits on `run.completed`, so `NEXT_CYCLE` (index 20) is the marker
stage that legitimately stays `pending` on a completed run. The suite asserts
the real contract: `completed is True`, `stage_index >= 20`, stages `[:20]` all
`ok`/`skipped`, `stages[20] == NEXT_CYCLE`. [V]

---

## 6. Test evidence

```
$env:PYTHONPATH = ...\backend
$env:USE_TEMPORAL = "false"
$env:DATABASE_URL / TEST_DATABASE_URL =
    postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test
python -m pytest tests/test_cycle_run_repository.py -q
```
Result:
```
.......                                                                  [100%]
7 passed in 35.36s
```

Regression:
```
python -m pytest tests/test_phase3_synthetic_vertical_slice.py -q
....                                                                     [100%]
4 passed in 0.42s
```
`python -m compileall -q app tests` → OK.

---

## 7. Notes / limitations

- [X] `cycle_runs` is the ONLY durability surface for loop runs; `_snapshot`
  (transient) and `_version` (guard) are never serialized — per 4A.
- [X] The migration file is validated headless against scratch PG, not the dev
  DB (no destructive infra authorized). The `migrate` container was NOT rebuilt;
  production deployment applies it via the existing migrate image path.
- [X] 4B touches only persistence; advisory source, governance binding
  (recommendation_id:vN:material_hash), and OutcomeLedger linkage land in 4C/4F.
- [B] Docker engine was down at first run (tests skipped via the TCP probe);
  restarted Docker + `docker compose start postgres redis` restored the stack —
  not a product regression.