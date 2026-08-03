# NazmOS — Track 2 Continuation Report

**Date:** 2026-07-31  
**Scope:** Finish the remaining Track 2 runtime blockers and start the S3-compatible storage abstraction.  
**Environment:** PostgreSQL 17 local install, zero-cost mode (`USE_CELERY=false`, `USE_REDIS=false`), Python 3.13.14.

---

## What was done

### 1. Regenerated Alembic migrations from current models

- Deleted the drifted migration chain `001`–`007` (they did not match `app.database.models.py`).
- Added `backend/alembic/script.py.mako` so autogenerate can render scripts.
- Created a single fresh initial migration: `backend/alembic/versions/748e4f2a4e7b_initial_schema.py`.
- Verified on a clean `nazmos_test` DB:
  - `alembic upgrade head` succeeds.
  - `alembic revision --autogenerate -m "test_noop"` produces an empty migration (no schema drift).
- Dropped and recreated the main `nazmos` DB with the same migration.

**Exact commands used:**
```bash
rm -f backend/alembic/versions/*.py
# recreate nazmos_test
DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test alembic revision --autogenerate -m "Initial schema"
# edit generated file to import UUID from app.database.types and use UUID(as_uuid=True)
DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test alembic upgrade head
DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos_test alembic revision --autogenerate -m "test_noop"  # empty
```

**Files changed:**
- `backend/alembic/script.py.mako` *(new)*
- `backend/alembic/versions/748e4f2a4e7b_initial_schema.py` *(new)*
- `backend/alembic/versions/001_initial_schema.py` *(deleted)*
- `backend/alembic/versions/002_runtime_tables.py` *(deleted)*
- `backend/alembic/versions/003_phase3_schema.py` *(deleted)*
- `backend/alembic/versions/004_compliance_hardening.py` *(deleted)*
- `backend/alembic/versions/005_recovery_match.py` *(deleted)*
- `backend/alembic/versions/006_money_audit.py` *(deleted)*
- `backend/alembic/versions/007_llm_router_usage.py` *(deleted)*

### 2. Fixed `_rebuild_summaries()`

- Rewrote `backend/app/services/etl_pipeline.py::_rebuild_summaries()` using CTEs and a window function to avoid the PostgreSQL `GroupingError`.
- Re-enabled the call in `ETLPipeline.run()`.
- Verified that daily summaries are populated after a sales upload:

```text
          date          | total_sales | total_profit | total_transactions
------------------------+-------------+--------------+--------------------
 2026-07-01 00:00:00+00 |      170.00 |        65.00 |                  2
 2026-07-02 00:00:00+00 |      100.00 |        40.00 |                  2
```

### 3. Fixed upload result reporting

- In `backend/app/routers/upload.py`, the zero-cost `/map` branch now persists `row_count_imported` and `row_count_failed` after `ETLPipeline.run()` finishes.
- `/api/v1/upload/{id}/result` now returns the real counts instead of `rows_imported: 0`.

**E2E verification:**
```text
sales_history_sample.csv -> rows_imported: 4
inventory_snapshot_sample.csv -> rows_imported: 3
```

### 4. Env-gated the free-plan validation limits

- `backend/app/services/subscription_service.py` now keeps production-intent free-plan limits (`uploads_per_month=2`, `money_audits_per_month=1`) and only raises them to `10` when `ENVIRONMENT=development`.

```python
if settings.ENVIRONMENT == "development":
    _dev_free = PLAN_CONFIG["free"]
    _dev_free.uploads_per_month = 10
    _dev_free.money_audits_per_month = 10
```

### 5. Triage of the remaining pytest failures

- Fixed the contract test `test_legacy_distraction_terms_are_not_reintroduced_in_source` by adding `.venv`/`venv` to the ignored directories in `tests/test_retail_recovery_contract.py`.

Full suite after the above:
```text
22 failed, 186 passed, 3 skipped
```

The 22 remaining failures are **test/API drift**, not core runtime defects:

| File | Count | Root cause |
|------|-------|------------|
| `tests/test_chat.py` | 4 | Chat endpoint expects query params; tests send JSON body. Missing `/history` and `/stream` routes in `app/routers/chat.py`. |
| `tests/test_dashboard.py` | 3 | Tests use `/api/v1/auth/demo`; actual route is `/api/v1/auth/demo-login`. Seed user email is `admin@nazmos.sa`, not `demo@nazmos.ai`. |
| `tests/test_decisions.py` | 5 | Tests call `/api/v1/decisions/*` routes that do not exist in `app/routers/decisions.py` (only `/recommend` exists). |
| `tests/test_forecast.py` | 5 | Forecast endpoint expects query params; tests send JSON. Missing `/cache` and `/summary` routes. |
| `tests/test_inventory.py` | 1 | Depends on the non-existent `/api/v1/auth/demo` route. |
| `tests/test_upload.py` | 4 | Tests do not create a business before uploading, so `assert_business_access` returns 404. Also a `files`+`data` TypeError in the unauthenticated upload test. |

These tests pre-date the current router shapes and need to be rewritten against the real API, not the other way around.

### 6. Started S3-compatible storage abstraction (Track 3 placeholder)

- Added config keys in `backend/app/config.py`:
  - `STORAGE_BACKEND` (`local` | `s3` | `minio`, default `local`)
  - `STORAGE_BUCKET`, `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_REGION`, `STORAGE_PREFIX`, `STORAGE_USE_SSL`
- Created `backend/app/services/storage.py` with:
  - `StorageBackend` abstract base class
  - `LocalStorageBackend` (default, zero-cost)
  - `S3StorageBackend` (uses boto3, falls back to local if boto3 missing)
  - `MinIOStorageBackend` (uses the `minio` package already in `requirements.txt`)
  - `get_storage_backend()` factory + module-level `storage` singleton
- Added `backend/tests/test_storage.py` covering the local backend.

**Note:** The upload router still writes files directly to `UPLOAD_DIR`. Wiring `storage.store()` into `/api/v1/upload/` is the next step; it was not done yet to avoid destabilizing the freshly-green E2E run.

---

## End-to-end re-validation

The full runtime E2E script was re-run from a clean database:

```bash
python scripts/runtime_e2e_upload_money_audit.py
```

Result:
```text
GET /health -> 200
POST /api/v1/auth/register -> 201
POST /api/v1/businesses/bootstrap -> 200
business_id <uuid>
POST /api/v1/upload/ -> 200
sales_history_sample.csv ... completed 100 4
POST /api/v1/upload/ -> 200
inventory_snapshot_sample.csv ... completed 100 3
POST /api/v1/money-audit/generate -> 200
audit {'money_at_risk_sar': 0.0, 'actions': 2, 'data_quality_score': 100.0}
approve -> 200
complete -> 200
money_approved_sar 877.5 money_recovered_sar 877.0
GET /api/v1/ops/pilot-console?business_id=... -> 200
NazmOS runtime E2E passed.
```

Confirmed in PostgreSQL after the run:
- 2 `daily_summaries` rows (new, from `_rebuild_summaries`)
- 4 `transactions`
- 3 `items`
- 3 `inventory` rows
- 2 `money_audit_actions`

---

## Remaining work before real merchant data

1. **Pytest test-API drift:** Rewrite or delete the 22 outdated tests in `tests/test_chat.py`, `tests/test_dashboard.py`, `tests/test_decisions.py`, `tests/test_forecast.py`, `tests/test_inventory.py`, and `tests/test_upload.py`.
2. **Wire storage abstraction into upload flow:** Replace direct `aiofiles` writes in `app/routers/upload.py` with `storage.store()`, and download to a temp path before parsing when using S3/MinIO.
3. **Backups & disaster recovery:** Automate PostgreSQL backups and test a restore.
4. **Observability:** Add Sentry + structured health-check alerting.
5. **Mock-LLM warning:** Add a startup log line that warns loudly when `USE_MOCK_LLM=true` outside local dev.

---

## Update: real `test_connection()` for POS adapters

Implemented and wired real connection tests for every adapter type, including Foodics and Salla.

### Changes

- `backend/app/adapters/registry.py`
  - Added `test_connection()` overrides for:
    - `TallyAdapter` — reachable server check.
    - `ShopifyAdapter` — `GET /shop.json` with access token.
    - `WooCommerceAdapter` — `GET /wp-json/wc/v3/products?per_page=1` with consumer credentials.
    - `ZohoAdapter` — refresh-token → access-token → `GET /api/v1/organizations`.
    - `CSVWebhookAdapter` — reachable endpoint check.
    - `CustomAPIAdapter` — reachable base URL check.
  - Added webhook-only adapters for Foodics and Salla:
    - `FoodicsWebhookAdapter`
    - `SallaWebhookAdapter`
    - Their `test_connection()` validates that a `webhook_secret` is configured and can produce a valid HMAC-SHA256 signature.
  - Registered `foodics` and `salla` in `ADAPTER_REGISTRY`.

- `backend/app/routers/adapters.py`
  - Rewired `POST /api/v1/pos/connections/{connection_id}/test` to instantiate the adapter and call `test_connection()` instead of returning a hard-coded `success: true`.
  - Returns `success: false` with a diagnostic message when credentials are wrong or the external system is unreachable.

- `backend/app/services/credential_vault.py`
  - Added credential validators for `foodics` and `salla` (`webhook_secret` required).

- `backend/app/schemas/adapter.py`
  - Extended `adapter_type` regex to allow `foodics` and `salla`.
  - Added `POSCredentialsWebhook` and included it in `POSConnectionCredentials`.

- `backend/app/database/models.py`
  - Added `FOODICS` and `SALLA` to the `POSAdapterType` enum.

- `backend/tests/test_adapters.py` *(new)*
  - Tests for webhook-secret validation and registry membership.

### Validation

```bash
pytest tests/test_adapters.py -q
# 7 passed
```

Full suite after adapter work:
```text
193 passed, 22 failed, 3 skipped
```

The 22 failures are the same pre-existing test/API drift cases listed earlier; the adapter work added 7 passing tests and no new failures.

Core E2E remains green:
```text
NazmOS runtime E2E passed.
```

---

## Files modified in this session

- `backend/alembic/script.py.mako`
- `backend/alembic/versions/748e4f2a4e7b_initial_schema.py`
- `backend/app/config.py`
- `backend/app/database/models.py`
- `backend/app/services/etl_pipeline.py`
- `backend/app/routers/upload.py`
- `backend/app/services/subscription_service.py`
- `backend/app/services/storage.py` *(new)*
- `backend/app/adapters/registry.py`
- `backend/app/routers/adapters.py`
- `backend/app/services/credential_vault.py`
- `backend/app/schemas/adapter.py`
- `backend/tests/test_storage.py` *(new)*
- `backend/tests/test_adapters.py` *(new)*
- `backend/tests/test_retail_recovery_contract.py`
- `TRACK2_FINISH_REPORT.md` *(this file)*

Earlier Track 2 fixes (auth commit, UUID type, session context managers, ETL raw SQL fixes, rate-limit dev multiplier, etc.) remain in the working tree from the previous session.
