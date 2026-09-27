# NazmOS Pilot Operations Runbook

Commands below are the actual commands executed and verified during the
Phase 4I final acceptance gate on branch `phase1-core-infra-replacements`
(HEAD `6078008`). Do not substitute unreviewed commands.

---

## 1. Prerequisites

- Python 3.14.4, pytest 9.0.3. Workdir is `backend` with PYTHONPATH set:
  `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend`.
- Postgres is provided by the `nazmos-postgres-4h` container (host port 5432,
  app role `nazmos` / password `nazmos_dev`). The compose runtime DBs
  (`nazmos_latest_merged-postgres-1`) authenticate as `nazmos` / `nazmos_v5_dev`.
- Temporal server is the compose `temporal` service
  (`temporalio/auto-setup:1.29.7`, host port 7233) + `redis` service.
- `USE_TEMPORAL=false` mirrors CI's "Backend tests with PostgreSQL" job for all
  non-Temporal gates.

## 2. Re-verify the pilot gate (verified green this session)

```powershell
# workdir: backend
$env:USE_TEMPORAL="false"
python -m pytest tests/phase4 -q                                   # 43 passed
python -m pytest tests/phase4/test_phase4i_ops_drills.py -q        # 6 passed
```

The 4I-D environment line stays: `JEV_LIVE=False JEV_ENABLED=False
BASE_URL='https://system-one.dev/v1/systemone'`. Shadow/mocked mode is the pilot
contract; any run flipping `JEV_ENABLED` live is out of contract.

## 3. Re-verify the durable repository + RLS + security gates

```powershell
# workdir: backend, Postgres UP on 5432
$env:USE_TEMPORAL="false"; Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
python -m pytest tests/test_cycle_run_repository.py -q                       # 7 passed
python -m pytest tests/test_phase4_loop_console.py tests/test_rls_predicate_indexes.py tests/security/test_celery_rls_tenant_context.py -q  # 73 passed
python -m pytest tests/test_security_acceptance.py -q                        # 9 passed (incl. both Postgres-gated)
python -m pytest tests/security -q                                           # 237 passed
```

## 4. Re-verify the Temporal substrate (real server, no skips)

```powershell
cd H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED
docker compose start postgres redis temporal   # non-destructive; existing containers/volumes
# wait for port 7233 to answer TCP
cd backend
$env:USE_TEMPORAL="true"
$env:TEMPORAL_ADDRESS="127.0.0.1:7233"
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
python -m pytest tests/temporal -q             # 29 passed, 0 skipped
```

`tests/temporal/conftest.py` connects to the external server, builds one
in-process production `build_worker`, and truncates all tables between tests.
`DATABASE_URL` is Postgres → zero scenarios skip.

## 5. Restart / recovery matrix (verified behavior)

| Situation | Behavior | Action |
|---|---|---|
| Mid-run restart, EXECUTION `running` | converges to guarded `unconfirmed` receipt; no blind re-run | let it converge; `run_one_stage` |
| Same trigger token after completion | returns the EXISTING completed run | new token for a new cycle |
| Stale concurrent writer | `CycleRunConflictError`; completed runs never bump version | reload, retry latest |
| Approval material changed | `approval_material_mismatch` → execution REFUSES | fix binding, re-approve |
| Kill switch | `EXECUTION_ENABLED=false` → `ExecutionDisabledError`, no execute path | flip config, restart worker |
| External outcome unknown after restart | `verification_status=unverified`, reconciliation reason `unconfirmed_external_outcome_after_restart` | retain receipt; re-message evidence |

## 6. Observability

`loop_console` GET-only read surfaces: `build_cycle_read_model(run)`
(`cycle/advisory/governance/approval/execution/reconciliation/measurement/
verification/learning` + `read_model_version`), `compute_lifecycle(run)`, and
`build_cycle_summary(run)`. Honest labels: `execution.synthetic=True`,
`approval.mode=simulated_owner_approval` + `simulated=True`,
`governance.certified_by=deterministic-governance`.

## 7. Live-execution boundary (deliberate)

The synthetic execute path (`synthetic=True`) is the only execute path the pilot
exercises. Real external execution is behind `EXECUTION_ENABLED` and requires a
real owner-auth identity decision (see `PHASE_4I_PILOT_AUTONOMY_POLICY.md` §3).

## 8. Upgrade path

Migrations ff13–ff15 (`cycle_runs`, `cycle_runs_rls_coverage`) are the single
alembic head. `procurement.supplier_risk` is registered in
`app/security/ai_policy.py` `AI_CAPABILITIES` (14 capabilities + flags).
Re-point `JEV_BASE_URL`/`JEV_API_KEY` only when leaving shadow mode; the code
still labels `source="jev"` solely for real replies and never overrides
deterministic ground truth.

## 9. Do not

- Do not set `EXECUTION_ENABLED=true` in a shadow pilot.
- Do not run `docker compose down -v` (destroys volumes).
- Do not commit/push from this branch without a release review.