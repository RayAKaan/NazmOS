# PHASE 4E — Revalidate State Versions + Evidence Watermark Across a Persisted Cycle

**Status: DONE [V]** — the persisted-cycle revalidation gate (4A contract test
plan item 4E). A resumed `CycleRun` may not advance past its pinned baseline
when the evidence the resume projects can no longer reproduce it. Drift is a
hard block — never a blind retry — and no stage attempt is consumed. Covered by
a new DB-free suite (6) and a Postgres-backed Temporal scenario F (7 total in
`tests/temporal`, 6 pre-existing). Full regression green.

## Result (TL;DR)

`business_cycle_advance` now revalidates the resumed cycle against the live
evidence BEFORE awarding the next stage: `CycleOrchestrator.revalidate_persisted(run)`
recomputes the state version (`project_state`) and the evidence watermark
(max `observed_at` over accepted records) from the exact evidence the advance
will project, and compares both to the persisted `starting_state_version` /
`evidence_watermark` pinned by STATE_PROJECTION (4A/4B snapshot seam). Any
mismatch — evidence changed underneath a persisted cycle, watermark rolled
back/forward, or out-of-scope records leaking in — yields `ok=False` and the
activity returns a `blocked=True` cursor with the JSON-safe verdict persisted in
`state_output["revalidation"]`. A worker-restart resume replaying the **same**
payload keeps revalidating `consistent` (that is scenario C's guarantee, now
made explicit by 4E). Runs not yet past STATE_PROJECTION have nothing pinned and
are allowed (`not_pinned`), so fresh cycles are unaffected. Wiring is deliberately
single-seam (advance only): drift returns, it does not raise, so reconcile/retry
never re-queues a drift-blocked stage.

## Deliverables

| Artifact | Source | Evidence |
|---|---|---|
| `CycleOrchestrator.revalidate_persisted(run)` (new) | `app/services/business_loop/cycle.py` | DB-free suite (6) + temporal scenario F |
| Revalidation gate in `act_business_cycle_advance` (edit) | `app/orchestration/temporal/activities.py` | drift blocks, no attempt consumed (scenario F) |
| `tests/test_phase4_cycle_revalidation.py` (new, DB-free) | `backend` | 6/6 passed |
| Scenario F in `tests/temporal/test_cycle_run_workflow.py` (edit) | `backend` | 7/7 cycle-workflow tests passed |
| `PHASE_4E_REPORT.md` + `MIGRATION_MATRIX.md` §11 4E row | repo root | — |

## Verdict model

Revalidation returns a plain JSON-safe dict (it rides the durable `_cycle_cursor`):

```
{ok, status, recomputed_state_version, persisted_state_version,
 recomputed_watermark, persisted_watermark, cross_scope}
```

`status` ∈ `consistent | not_pinned | state_version_drift | watermark_drift |
cross_scope` (semicolon-joined when multiple).

- `starting_state_version == ""` (pre-STATE_PROJECTION) → `not_pinned`, `ok=True`.
- Recomputed version == persisted version AND recomputed watermark == persisted
  watermark → `consistent`, `ok=True`.
- Any mismatch on a pinned run → `ok=False`; verdict keys let an operator see
  exactly what drifted and by how much.
- `cross_scope` counts accepted records whose `tenant_id`/`business_id` fall
  outside the run's scope (defense-in-depth atop the 4B tenant-scoped load).

## Advance wiring (final)

`business_cycle_advance` (activities.py) now: `repo.load` → rehydrate snapshot →
rebuild evidence exactly as the 4D advance does → **`revalidate_persisted(run)`**
→ on `ok=False`: persist `last_error = "revalidation_blocked:{status}"` +
`state_output["revalidation"]`, save, and return
`_cycle_cursor(run, advanced=False, done=False, blocked=True, revalidation=verdict)`.
The stage machine is never advanced; attempts stay untouched.

## Evidence

```
# new 4E DB-free suite
$env:PYTHONPATH="H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend"
$env:USE_TEMPORAL="false"
python -m pytest tests/test_phase4_cycle_revalidation.py -q
=> 6 passed

# Postgres-backed: scenario F unit (drifted resume blocks; same-evidence resumes)
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
$env:TEST_DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
$env:USE_TEMPORAL="true"
python -m pytest tests/temporal/test_cycle_run_workflow.py -q
=> 7 passed   (6 pre-existing 4D/4C scenarios + new 4E scenario F)

# full temporal suite
python -m pytest tests/temporal -q
=> 24 passed (none skipped on Postgres)

# loop + slice + wiring regression (DB-free)
$env:USE_TEMPORAL="false"
python -m pytest tests/test_phase3_synthetic_vertical_slice.py \
  tests/test_phase4_foundation.py tests/test_phase4_jev_advisory.py \
  tests/test_phase4_cycle_revalidation.py tests/test_business_loop_modules.py \
  tests/test_business_decision_loop_v1.py tests/test_orchestration.py \
  tests/test_execution_path_clarity.py -q
=> 103 passed

# Postgres-backed repository + execution-path contract
python -m pytest tests/test_cycle_run_repository.py \
  tests/test_execution_path_clarity.py::test_same_action_both_paths_contract -q
=> 8 passed

python -m compileall -q app tests alembic  => OK
```

Baseline macro-regression (from 4D, unchanged by 4E's additive gate):
`python -m pytest tests -q --ignore=tests/temporal
--ignore=tests/test_n2_probe_inventory_emission_real.py
--ignore=tests/test_n2c_probe_full_json.py -p no:cacheprovider`
=> 1445 passed, 1 xfailed, 0 failed.

## Notes / limitations

- **[X] Reconcile is intentionally NOT a revalidation seam.** A drift verdict is
  *returned* (never raised), so `business_cycle_reconcile` is not triggered by a
  drift block, and reconcile's job stays budget-gating, not revalidation-gating.
  The blocked verdict is persisted and visible on the row, so 4G's read-only
  console can surface it.
- **[X] The gate is advance-boundary only.** `run_one_stage` itself (via
  `local_business_cycle_run`, DB-free) does not revalidate — the durable gate
  lives where the persisted cursor crosses into a new stage, which is the
  activity. Same-evidence resume keeps scenario C (worker restart) green.
- **No migrations**: 4E reads/writes existing 4B columns (`starting_state_version`,
  `evidence_watermark`, `state_output`, `last_error`).
- **No commits/pushes; no infra changes.** Dev/production DBs untouched.

## Next (4F+)

4F links executed actions → `OutcomeRecord` → V1 `OutcomeLedger` (VERIFIED
requires measured impact + distinct state versions), then 4G read-only console
endpoints, 4H hardening, 4I final acceptance.