# PHASE_4A — Runtime Contract Report (Business Loop Durability & Lifecycle)

> This is the source-of-truth contract for Phase 4 (MASTER_PLAN §16.2 → durable runtime).
> Scope: freeze the durable `CycleRun` payload and serialization keys, the 21-stage
> lifecycle + legal transitions, the `cycle_runs` migration design (chained from head
> `ff13_drop_celery_upload_task`), the recovery/idempotency rules (reconcile-before-retry,
> no blind retries), and the Phase 4 test plan. Evidence labels follow repo convention
> [V] verified now / [I] inferred-unverified / [X] contradicted / [!] blocker / [B] baseline.

## 1. Frozen `CycleRun` contract (durable payload)

`CycleRun` (`backend/app/services/business_loop/cycle.py:98`) is the only cycle artifact
that becomes durable in Phase 4. `serialize()` (cycle.py:116) is the durability seam —
the exact key set below is what the DB row must round-trip **losslessly**:

| Key | Type | Notes | Evidence |
|---|---|---|---|
| `cycle_id` | str (64) | `cycle-<sha256[:24]>` of `tenant:business:trigger:trigger_token`; idempotency anchor | cycle.py:64 [V] |
| `tenant_id` | str (64) | loop tenant scope | cycle.py:98 [V] |
| `business_id` | str (36) | RLS anchor column (UUID) | [V] |
| `trigger` | str (64) | cycle trigger kind | [V] |
| `trigger_token` | str (128) | dedupe token for the trigger | [V] |
| `created_at` | str (ISO) | `_now_iso()` UTC seconds | cycle.py:44 [V] |
| `starting_state_version` | str (64) | pre-cycle state version | [V] |
| `evidence_watermark` | str (64) | accepted-evidence digest watermark | [V] |
| `completed` | bool | terminal flag | [V] |
| `stage_index` | int | resumption cursor | [V] |
| `last_error` | str | last stage error (recovery context) | [V] |
| `state_output` | dict | non-`_`-prefixed outputs only (DLP-safe serializer drops underscores) | cycle.py:129 [V] |
| `stages` | list[dict] | per-stage `{stage, status, attempts, error}` | cycle.py:130 [V] |

`_snapshot` is deliberately **not** serialized (business state is recomputed from evidence;
persisting it would freeze stale facts). [V] cycle.py:114

`CycleRepository` (cycle.py:142) `save/load` is the persistence seam; `InMemoryCycleRepository`
(cycle.py:152) keeps the synthetic slice DB-free. Phase 4B adds `PostgresCycleRepository`
with the same surface + `all()` + optimistic-concurrency version guard.

## 2. Lifecycle: 21 stages and legal transitions

`CycleStage.ordered()` (contracts.py:146-173) fixes 21 ordered stages. Phase 4B records
each stage's final `status`; legal per-stage status values:

- `pending` → `running` → `ok` | `failed` (retryable ≤ `CyclePolicy.max_retries_per_stage`, default 2)
- `skipped` is terminal-declared for a stage (e.g. no opportunities at `opportunity_detection` → all downstream `skipped`, cycle `completed=True` no-op) [V] cycle.py:88

Ordered stage list (the contract the console + workflow enforce):

1. `evidence_discovery` 2. `ingestion` 3. `validation` 4. `state_projection`
5. `freshness_assessment` 6. `opportunity_detection` 7. `impact_calculation`
8. `action_candidates` 9. `advisory` 10. `advisory_validation` 11. `recommendation`
12. `governance` 13. `approval_wait` 14. `preflight` 15. `execution` 16. `reconciliation`
17. `verification` 18. `learning_eligibility` 19. `learning` 20. `cycle_summary` 21. `next_cycle`

Resume rule: stage cursor = first stage whose status ∉ {`ok`, `skipped`}; a `failed`
stage resumes by retry (bounded), never by skipping forward. [V] cycle.py:189+ orchestrator

## 3. Migration design (`ff14_cycle_runs`)

Chained from verified single head `ff13_drop_celery_upload_task` (`python -m alembic heads` -> `ff13_drop_celery_upload_task`) [V].

`cycle_runs` table (Postgres; SQLite batch-safe for dev):

- `id` UUID PK default `gen_random_uuid()` (model: `uuid.uuid4`)
- `cycle_id` String(64) NOT NULL — the canonical idempotency key
- `tenant_id` String(64) NOT NULL
- `business_id` UUID NOT NULL FK → `businesses.id` ON DELETE CASCADE — RLS anchor
- `trigger` String(64) NOT NULL, `trigger_token` String(128) NOT NULL DEFAULT ''
- `created_at` DateTime(timezone=True) server_default `now()`
- `starting_state_version` String(64), `evidence_watermark` String(64)
- `stage_index` Integer NOT NULL DEFAULT 0
- `completed` Boolean NOT NULL DEFAULT false
- `last_error` Text NOT NULL DEFAULT ''
- `state_output` JSON NOT NULL DEFAULT '{}'::json
- `stages` JSON NOT NULL DEFAULT '[]'::json
- `schema_version` String(16) NOT NULL DEFAULT 'loop-v1'
- `version` Integer NOT NULL DEFAULT 1 — optimistic concurrency guard
- `updated_at` DateTime(timezone=True) server_default now() onupdate now()

Constraints / indexes:
- `UNIQUE (business_id, cycle_id)` → duplicate-trigger suppression + per-tenant uniqueness
- `idx_cycle_runs_tenant_lookup (business_id, created_at DESC)` → console list
- `CHECK (stage_index >= 0)`

RLS + grants follow the verified pattern from `b7c8d9e0f1a2` (RLS) + `ff11` (nazmos_app grants):
- add `cycle_runs` to the TENANT_TABLES list in the RLS migration family
- `ALTER TABLE cycle_runs ENABLE ROW LEVEL SECURITY`
- policy `business_id = app.current_tenant_id()` (using `nazmos_app` role) [V] migration b7c8d9e0f1a2
- `GRANT SELECT, INSERT, UPDATE, DELETE ON cycle_runs TO nazmos_app;` + sequence grants (idempotent `DO $$` block) [V] ff11 pattern

Downgrade = drop table (no legacy data migration needed; table is new in Phase 4).

## 4. Recovery & idempotency rules (Phase 4D backbone)

1. **Idempotent start**: `derive_cycle_id` over `(tenant, business, trigger, trigger_token)`.
   `PostgresCycleRepository.save` on an existing `(business_id, cycle_id)` returns the
   existing row (INSERT ... ON CONFLICT DO NOTHING then SELECT) — no duplicate cycle ever
   materialized. [V] cycle.py:64
2. **Reconcile-before-retry**: when a stage fails or a workflow run outcome is unknown
   (activity terminated), the **first** recovery step is loading the persisted stage cursor
   and reconciling external outcome state (e.g. via `execution` module / `execution_key`)
   — never a blind retry that duplicates an already-applied action. [V] execution.py `ExecutionIntent`
3. **Optimistic concurrency**: `save` writes only when persisted `version == run.version`;
   mismatch raises a concurrency error (defense against two workers mutating one run).
4. **Terminal protection**: once `completed=true`, `save` becomes a no-op (immutable
   history); stage transitions past `cycle_summary` require `next_cycle` to spawn a new
   run with a new `cycle_id`.
5. **No parallel ledgers**: the ONLY durable loop artifacts remain the V1 `OutcomeLedger`
   (verified outcomes) + `cycle_runs`. No second gateway/orchestrator/ledger is introduced. [I]

## 5. Phase 4 test plan

- **4B** `backend/tests/test_cycle_run_repository.py` (Postgres): create idempotent,
  tenant-scoped load, legal transition save, version-guard conflict, terminal no-op,
  serialize↔DB round-trip lossless (21-stage payload).
- **4C** `backend/tests/test_phase4_jev_advisory.py` (DB-free): typed advisory via the
  canonical `ai_gateway` entry; source attribution `mocked` (never `jev` for mock);
  out-of-contract advisory dropped; capsule DLP-clean.
- **4D** extend `backend/tests/temporal/` + `docker start` the stopped worker: real server,
  in-process production `build_worker`, durable dispatch, worker-restart recovery,
  duplicate suppression, reconcile-before-retry on unknown external outcome.
- **4E** revalidate state versions + evidence watermark across a persisted cycle.
- **4F** link executed action → `OutcomeRecord` → V1 `OutcomeLedger`; VERIFIED requires
  measured impact + distinct state versions.
- **4G** extend `backend/app/routers/loop_console.py` with read-only `GET /runs` (list) and
  `GET /runs/{cycle_id}` (detail), owner-gated via `assert_business_access`; IDOR tests
  in `tests/` (mirror existing loop-console IDOR suite).
- **4H** hardening: terminal protection, error inheritance in stage records, workflow
  retry policy reuse.
- **4I** compileall + full gate (baseline 260 [B] + Phase 3 loop/console/IDOR + Phase 4
  suites) + `PHASE_4_FINAL_ACCEPTANCE_REPORT.md` + MIGRATION_MATRIX §11.

## 6. Environmental anchors (verified this session)

- Postgres test credentials: `nazmos / nazmos_v5_dev @ localhost:5432/nazmos_test` — the
  conftest default (`nazmos_dev`) is stale; runs must pass `TEST_DATABASE_URL` +
  `DATABASE_URL` explicitly. [V]
- Alembic single head: `ff13_drop_celery_upload_task`. [V]
- Temporal container up (healthcheck flags *constitutionally* unhealthy due to its own bug);
  worker container currently stopped — 4D will `docker start` (start-only, no recreate). [V]
- SQLite fast suites run with `USE_TEMPORAL=false`; Temporal suite forces `USE_TEMPORAL=true`. [V] AGENTS.md

## 7. Status

PASS — contract frozen, migration design final, test plan locked. Nothing production-modified
in 4A (recon only).