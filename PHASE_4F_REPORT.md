# PHASE 4F — Verified Execution→Outcome Linkage → OutcomeLedger V1 (+ Learning Eligibility Gate)

**Status: DONE [V]** — the executed action → canonical `OutcomeRecord` → measurement
→ distinct-state-version verification → deterministic learning-eligibility gate →
existing `OutcomeLedger` V1 path is implemented on top of the complete 4A–4E stack.
No second ledger, learning store, or business-truth authority was created:
`OutcomeLedger` V1 stays authoritative and the ✱sanctioned✱ `VerifiedOutcomeLedger`
write path in `outcomes.py` is superseded by a readback-confirmed attach built on
V1. Covered by a new DB-free suite (30) and Postgres-backed Temporal Scenario G
(4 new, 28 total in `tests/temporal`). Full regression green.

## Result (TL;DR)

A cycle run that executed an action now carries a durable canonical association
(`outcome_linkage` in `state_output`) between the run
(tenant/business/cycle/execution/recommendation) and its outcome record, and the
verified result lands in `OutcomeLedger` V1 exactly once per execution. The loop's
previously hardcoded learning-eligibility flags in `_stage_learning_eligibility`
(always `True`) were replaced with COMPUTED gates: tenant-authorized (run is
tenant-scoped), quality-satisfied (evidence watermark fresh), and
attribution-sufficient (deterministic measurement, or a provider/fallback-attributed
signature — a Jev advisory alone can never authorize learning). `verify_outcome`
now REQUIRES distinct baseline/post state versions for VERIFIED: a reused identical
snapshot can never attribute change to the action. Captures are idempotent (the
ledger key derives from tenant+execution+recommendation; the persisted
`outcome_recorded` marker plus the V1 `ON CONFLICT` upgrade keep replays to ONE
row) and readback-confirmed — a bare best-effort `True` is never accepted as proof.
An execution with unknown approval is skipped, so it produces no verified outcome,
no ledger row, and no learning.

## Deliverables

| Artifact | Source | Evidence |
|---|---|---|
| `verify_outcome` distinct-version guard (edit) | `app/services/business_loop/outcomes.py` | DB-free suite (30) + protected 10-key `to_dict` regression |
| `learning_eligibility` `attribution_sufficient` + `state_versions_not_distinct` (edit) | `app/services/business_loop/outcomes.py` | DB-free suite (30) |
| `OutcomeLedger.row()` readback (new) | `app/services/outcome_ledger.py` | readback-confirmed attach tests |
| `app/services/business_loop/outcome_linkage.py` (new) | canonical linkage + attach module | DB-free suite (30) |
| `_stage_learning_eligibility` computed gates (edit) | `app/services/business_loop/cycle.py` | slice + temporal e2e (learning_eligible True/False) |
| `business_cycle_advance` attach wiring (edit) | `app/orchestration/temporal/activities.py` | Scenario G (4) |
| `tests/test_phase4_outcome_linkage.py` (new, DB-free) | `backend` | 30/30 passed |
| Scenario G in `tests/temporal/test_cycle_run_workflow.py` (edit) | `backend` | 28/28 cycle-workflow tests passed |
| `PHASE_4F_REPORT.md` + `MIGRATION_MATRIX.md` §11 4F row | repo root | — |

## The chain (as implemented)

```
executed action (state_output.execution, receipt ok)
  └─› VerificationStage   → OutcomeRecord via verify_outcome(outcome_id,
        recommendation_id/version, execution_key, baseline=run.starting_state_version,
        post=project_state(verification_evidence).state_version, measured→method)
                              REPORTED (no measurement) → OBSERVED (measured, no criteria)
                              → PARTIALLY_VERIFIED (one-sided/identical snapshots)
                              → VERIFIED (measured + method + DISTINCT versions)
  └─› LearningEligibilityStage → outcome_linkage (state_output) + computed gates:
        tenant_authorized = bool(run.tenant_id)
        quality_satisfied = evidence_watermark not in ("", "none")
        attribution_sufficient = attribution_sufficient(build_linkage().attribution_quality)
  └─› advance activity        → outcome_recorded marker persisted, then
  └─› OutcomeLedger V1        → row(key) readback-confirmed; verified=1 only for VERIFIED
```

## Verdict model

Attribution classifier (`attribution_quality`) is deterministic and never upgraded
by a provider:
`deterministic_measurement` (measured+method+VERIFIED/PARTIAL) dominates any
advisory; otherwise the exact advisory provenance is recorded —
`deterministic_advisory` / `provider_advisory` are candidate-sufficient,
`jev_advisory_only` NEVER is, `none` is nothing. `attribution_sufficient` =
{deterministic_measurement, deterministic_advisory, provider_advisory}.

`attach_outcome` returns a readback-confirmed `OutcomeAttachment`
(`recorded/attached_verified/row_present/row_verified/outcome_status/reason`).
Reasons distinguish `ledger_disabled`, `tenant_unscoped`, `record_skipped`,
`row_missing`, `verified_mismatch`. A run with no realized execution
(skipped/unknown approval) is NOT attached at all — no ledger row, verified or
otherwise.

## Advance wiring (final)

`business_cycle_advance` (activities.py): after the 4E revalidation gate and
`run_one_stage`, IF the run already produced an outcome record (never before
VERIFICATION, never for an execution with `ok=False`/skipped) AND the
`outcome_recorded` marker is absent → `attach_cycle_outcome(run)`; on success the
attachment (and the marker) are persisted with the run via `repo.save`. Capture is
best-effort and never blocks the cycle.

## Evidence

```
# new 4F DB-free suite
$env:PYTHONPATH="H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend"
$env:USE_TEMPORAL="false"
python -m pytest tests/test_phase4_outcome_linkage.py -q
=> 30 passed

# loop + ledger + repository + wiring regression (DB-free + Postgres-backed)
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
$env:TEST_DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
python -m pytest tests/test_cycle_run_repository.py tests/test_business_loop_modules.py \
  tests/test_phase3_synthetic_vertical_slice.py tests/test_phase4_cycle_revalidation.py \
  tests/test_phase4_outcome_linkage.py tests/test_outcome_ledger_v1.py \
  tests/test_loop_console.py tests/test_phase5_learning_loop.py tests/test_phase6_loop.py \
  tests/test_phase7_loop.py tests/test_phase8_loop.py -q
=> 110 passed

# full temporal suite (real server + production worker, Postgres)
$env:USE_TEMPORAL="true"
python -m pytest tests/temporal -q
=> 28 passed (none skipped on Postgres: 24 pre-existing 4C/4D/4E + 4 new Scenario G)

python -m compileall -q app tests alembic  => OK
```

Baseline macro-regression: `python -m pytest tests -q --ignore=tests/temporal
-p no:cacheprovider`
=> 1481 passed, 1 xfailed, 2 errors. The 2 errors are PRE-EXISTING and unrelated
to 4F: `tests/test_n2_probe_inventory_emission_real.py` and
`tests/test_n2c_probe_full_json.py` request a `sqlite_db` fixture that is not
defined in any `tests/**/conftest.py` (verified — fixture absent repo-wide; the
4D/4E reports had pushed them out with `--ignore` for the same reason). No 4F
code path touches the n2 probe surface.

## Acceptance checklist (4F master directive)

- [V] executed action → OutcomeRecord → measurement → verification → ledger chain
- [V] idempotency — key = sha256(tenant:execution_key:recommendation_id:recommendation_version)[:24]; replays coalesce (G2 + DB-free duplicate/concurrent tests)
- [V] estimate ≠ measured ≠ verified (expected vs observed vs status; measured-without-criteria is OBSERVED, estimate-only is REPORTED)
- [V] same state version can NEVER be VERIFIED (verify excludes it; eligibility reason `state_versions_not_distinct`)
- [V] Jev advisory alone can neither verify nor authorize learning (`jev_advisory_only` never sufficient; verify_outcome is pure — a Jev source is not even an input)
- [V] exact provider attribution survives the wire (row `provider`/`model`/`source` verbatim; Jev never injected as provider)
- [V] unknown execution (approval pending) → skipped → no outcome record, no ledger row, learning False (G4)
- [V] pending measurement (no post snapshot) → REPORTED, captured but never verified, `verified_outcomes()` empty (G3)
- [V] restart/replay-safe rebuild of linkage from persisted `state_output` (deterministic `build_linkage`)
- [V] tenant isolation — key divergence per tenant + `tenant_unscoped` refusal at attach
- [V] DLP-clean JSON-safe linkage (identifiers + SAR numbers only; `json.dumps`-safe dict)

## Notes / limitations

- **[X] The loop does NOT write `impact_ledger`.** The 4D/4F executions are
  synthetic dry-runs (`dry_run_execute`); `impact_ledger_service.record_impact`
  has no unique constraint on a deterministic key and is wired to
  nonexistent-intent findings. Writing it from the loop would manufacture ledger
  rows without a real finding/action. Documented boundary; the money-moving path
  flows through `app/orchestration` actions, not this loop.
- **[X] Ledger remains opt-in via `AI_OUTCOME_LEDGER_PATH`** (default `""` =
  `ledger_disabled`). Production should mount a filesystem path (e.g. on the
  persistent volume) to enable capture; linkage data is still durable in
  `cycle_runs.state_output` regardless.
- **[X] Postgres `cycle_runs` carries no ledger tenant column; `OutcomeLedger` V1
  has no tenant column.** Isolation is enforced at the KEY layer (tenant in the
  composite) and by the `tenant_unscoped` attach refusal. The global `loop_console`
  read of the ledger (pre-existing) remains a 4G-domain concern.
- **No migrations**: 4F writes to the existing `cycle_runs.state_output` and the
  existing SQLite `OutcomeLedger` V1 schema.
- **No commits/pushes; no infra changes.**
- **[X] Pre-existing n2 probe fixture breakage** (`sqlite_db` not found) — out of
  4F scope; flagged above with evidence.

## Next (4G+)

4G read-only console endpoints (tenant-scoped `OutcomeLedger` reads),
4H hardening (concurrent duplicate lock / reconciliation),
4I crash-resume acceptance.