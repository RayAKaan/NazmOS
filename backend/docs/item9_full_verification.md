# Item 9 — Full Suite Verification Report

Definitive runs against the migrated PostgreSQL test database
(`nazmos_test`, credentials supplied via `TEST_DATABASE_URL`) with
`PYTHONPATH=backend`.

## 1. Full pytest suite

```
$env:TEST_DATABASE_URL="postgresql+asyncpg://<user>:<password>@localhost:5432/nazmos_test"
python -m pytest tests/ -p no:cacheprovider -q --tb=no -rfE
```

Result (final, after resolving stale pre-existing test defects — see §5):
**1190 passed, 3 skipped, 1 xfailed, 1 failed** in 12:44.

The single failure is the pre-existing, environment-specific event-loop
teardown flake:

- `tests/security/test_celery_rls_tenant_context.py::TestSyncTenantContextAsyncCoverage::test_async_session_in_context_sees_only_own_tenant`

It FAILS only under a combined multi-thousand-test run (asyncpg
`RuntimeError: Event loop is closed` when the module-level `AsyncSessionLocal`
outlives a torn-down loop). It PASSES reliably in isolation (5.82s) and when the
whole file runs alone (7 passed in 1.76s). It is unrelated to any edit in this
session. Not hidden — recorded here for the record.

## 2. Item-scoped regressions (all green)

- `tests/regression/` (golden fixtures, canonical acceptance, F/D/E/H/G/I/root-cause): **55 passed, 1 xfailed**.
- `tests/regression/test_adversarial_matrix.py`: **31 passed** (incl. Item 8 `TestRootCauseAssertions`).
- `tests/test_decisions.py`: updated apply-decision business-scoped tests pass.
- `tests/test_chat.py`, `tests/test_dashboard.py`, `tests/test_zero_cost_sqlite_mode.py`, `tests/test_guest_audit.py`: pass.

## 3. Static / security gates

- `python -m compileall -q app tests` → **clean**.
- `bandit -r app --confidence-level medium --severity-level medium` → **clean**
  (only pre-existing intentional `# nosec` B608 dynamic-SQL escapes; no new findings
  in `actions.py`, `decisions.py`, `upload.py`, `pharmacy.py`, `finding_service.py`,
  `health.py`, `audits.py`).
- gitleaks config present (`.gitleaks.toml`), run via pre-commit (bandit + gitleaks).
  No new secret was introduced.
- No mypy/ruff/black tooling is pinned in `requirements.txt` or project config;
  the project's declared gates are bandit + gitleaks + pytest.

## 4. Migration / route / OpenAPI

- Alembic single head: `ff08_loc_grain_tenant_model` (verified via `alembic heads`
  and `alembic current`); the full chain upgrades cleanly to head on the test DB.
- Route inventory: 228 paths; all Item 7 touchpoints present
  (`/api/v1/actions/execute`, `/api/v1/actions/decisions/{id}/apply`,
  `/api/v1/pharmacy/lots`, `/api/v1/upload/{id}/progress`, `/health`,
  `/api/v1/money-audit/...`).
- `tests/test_openapi_contract.py` → **passes** after the intentional `apply_decision`
  `business_id` query param was folded into the committed golden
  (`backend/docs/openapi.json`, refreshed via `UPDATE_GOLDEN=1`).

## 5. Pre-existing test defects RESOLVED this session (not hidden)

1. `tests/test_etl_dedup.py` (3 failures) — stale against the canonical model:
   - `test_row_hash_matches_decision_spec` mirrored the OLD 2-field hash; updated
     to the ff08 canonical fields (`location_id`, `source_transaction_id`) → **passes**.
   - `test_reimport_is_idempotent` — SQLite cannot use a 4-column partial unique
     index as an `ON CONFLICT` arbiter; marked `xfail` with a docstring pointing to
     the overriding PostgreSQL test (`TestETLIntegration`). The re-import row did
     duplicate on SQLite but this is a SQLite limitation, not a production bug —
     on Postgres the ON CONFLICT suppresses it (verified by `TestETLIntegration`).
   - `test_changed_quantity_is_new_row` — passes once the row-hash field set matches
     the canonical model (different quantities → different hashes → new rows).
2. `tests/test_agent_actions.py::test_approve_restock_action_writes_outcome` — the
   fixture inserted a user and business but never linked them (`owner_id` null), so
   the Items 2–3 service-boundary RBAC gate (`user_has_capability(..., "can_approve_actions")`)
   correctly refused approval. Fixed the FIXTURE to set `owner_id` → **passes**.
3. `tests/test_openapi_contract.py` — golden refreshed for the intentional
   `business_id` query param added in Item 7 → **passes**.

## 6. Remaining known environmental flake (NOT a code defect)

- The single `test_celery_rls_tenant_context` async teardown flake above. It has
  passed every isolated/whole-file invocation across this session.

## Files changed for Item 9 (test-only; no production code)

- `backend/tests/test_etl_dedup.py` — canonical hash fields + idempotency xfail.
- `backend/tests/test_agent_actions.py` — fixture sets `owner_id`.
- `backend/docs/openapi.json` — refreshed golden (intentional `business_id` param).
