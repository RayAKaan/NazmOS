# NazmOS — Production Hardening Pass Verification Report

**Date:** 2026-08-07  
**Scope:** Fix/refactor as many production blockers as possible inside the sandbox (no Docker/Postgres/Redis).

---

## What was fixed / refactored

### 1. Production config hardening
- **`backend/app/config.py`**
  - Added `CREDENTIAL_MASTER_KEY` setting.
  - Added production validators:
    - `USE_MOCK_LLM` must be `False` in production.
    - `CREDENTIAL_MASTER_KEY` required and ≥32 chars in production.
    - `FOODICS_WEBHOOK_SECRET` / `SALLA_WEBHOOK_SECRET` validated (soft recommendation).
  - `get_settings()` now fails fast in production for dev secrets, missing Sentry, mock LLM, or missing credential master key.

- **`backend/app/utils/startup_checks.py`**
  - Added `validate_production_secrets()` called on every startup.
  - Fails closed if production secrets are missing or still defaults.

### 2. Credential vault hardening
- **`backend/app/services/credential_vault.py`**
  - Removed hardcoded production fallback.
  - Logs a warning in development if `CREDENTIAL_MASTER_KEY` is not set.
  - Production safety is enforced by config validators.

### 3. PII redaction improvements
- **`backend/app/utils/logger.py`**
  - Added regex-based redaction for emails, Saudi mobile numbers, and Saudi IDs in free-form strings.
  - `redact_pii()` now redacts strings inside lists and scalar values, not just dict keys.
  - Log messages themselves are redacted before emission.

### 4. Upload router storage-abstraction cleanup
- **`backend/app/routers/upload.py`**
  - Refactored `upload_file()` to use the existing `_resolve_local_parse_path()` helper instead of duplicating object-storage download logic.
  - Ensures temporary parse files are always cleaned up after parsing.
  - No functional change for local dev; production S3/MinIO path is now cleaner and less error-prone.

### 5. Robust POS/e-commerce item matching
- **`backend/app/adapters/item_resolver.py`** (new)
  - Shared resolver that matches incoming order lines to the merchant catalog using:
    1. barcode (exact)
    2. SKU (exact)
    3. name starts-with
    4. legacy fuzzy contains fallback
- **`backend/app/adapters/foodics.py`**
  - Replaced fuzzy-only name matching with `resolve_item()`.
  - Returns `unresolved_items` when a webhook line cannot be mapped.
- **`backend/app/adapters/salla.py`**
  - Same refactor as Foodics.
  - Extracts `sku`, `barcode`, and `product_sku` fields from Salla payloads.

### 6. Incident response runbooks
- **`RUNBOOKS.md`**
  - Added Section 8: PII / Personal Data Breach Response (PDPL) — detection, containment, notification, post-incident.
  - Added Section 9: Credential Master Key Rotation procedure.

### 7. Tests
- **`backend/tests/test_production_hardening.py`** (new)
  - PII redaction for known keys and nested fields.
  - Email/phone pattern redaction in free-form strings.
  - Production config validators reject mock LLM and missing credential master key.
  - `resolve_item()` prefers barcode match and returns `None` when no match.

---

## Verification results

### Backend tests
```
pytest -q
253 passed, 69 skipped, 37 warnings, 2 errors in 12.70s
```
- The 2 errors are the unchanged environmental PostgreSQL connection failures in `tests/test_rls_enforcement.py`.
- Baseline before this pass: `246 passed, 69 skipped, 37 warnings, 2 errors`.
- Net change: **+7 passing tests**, no new failures.

### Frontend
```
npm run lint  → passed
npm run build → passed, 31 static routes prerendered
```

### Workspace cleanliness
- `frontend/node_modules` removed.
- `frontend/.next` removed.
- All `__pycache__` / `.pyc` files removed.
- `.pytest_cache` removed.
- No DB files left in `backend/` root.

---

## Files changed / created

### New files
- `backend/app/adapters/item_resolver.py`
- `backend/tests/test_production_hardening.py`
- `PRODUCTION_HARDENING_PASS_VERIFICATION_REPORT.md` (this file)

### Modified backend files
- `backend/app/config.py` — production secret validators.
- `backend/app/utils/startup_checks.py` — production secret startup checks.
- `backend/app/services/credential_vault.py` — remove hardcoded fallback.
- `backend/app/utils/logger.py` — pattern-based PII redaction.
- `backend/app/routers/upload.py` — consistent storage abstraction usage.
- `backend/app/adapters/foodics.py` — robust item resolution.
- `backend/app/adapters/salla.py` — robust item resolution.

### Modified documentation
- `RUNBOOKS.md` — PII breach response and credential key rotation.
- `LEAP_STRATEGY_IMPLEMENTATION_VERIFICATION_REPORT.md` — rephrased to avoid legacy distraction term.

---

## What could NOT be fixed in the sandbox

The following blockers require infrastructure, credentials, or third-party access that the sandbox does not provide:

1. **Celery/Redis production runtime validation** — no Redis service running.
2. **Sentry DSN configuration** — needs a real Sentry project.
3. **Daily backups + restore drill** — needs production object storage and scheduling.
4. **Live connector validation** — needs sandbox credentials from Salla/Zid/Foodics/Qoyod.
5. **OAuth flows** — needs registered apps with each platform.
6. **Penetration test / security certification** — needs third-party assessor.
7. **WhatsApp Business API integration** — needs Meta BSP account.
8. **PWA/mobile owner mode** — needs build/deploy pipeline, though the web foundation exists.
9. **Public case studies** — needs real merchant pilot data.
10. **Accountant/Monshaat partner program** — needs operational partnerships.

---

## Updated critical-blocker checklist

| Blocker | Status before | Status after |
|---|---|---|
| Object storage wired into upload router | Partial | ✅ Clean abstraction, temp cleanup robust |
| Celery/Redis production path validated | Code only | ⬜ Needs live services |
| Daily backups + restore drill | Scripts only | ⬜ Needs scheduling + storage |
| PDPL compliance program | Placeholders | ✅ Deletion/export endpoints exist; PII breach runbook added |
| PII redaction audited | Not done | ✅ Pattern + key redaction tested |
| Sentry DSN configured | Missing | ⬜ Needs real DSN |
| Credential master key enforced | Hardcoded fallback | ✅ Production validators + startup checks |
| Connector live validation | Docs-only | ⬜ Needs sandbox credentials |
| Pen test | Not done | ⬜ Needs third party |
| Incident response runbooks | Basic | ✅ PII breach + key rotation added |

---

## Recommended next actions (outside sandbox)

1. Set `CREDENTIAL_MASTER_KEY`, `SENTRY_DSN`, and webhook secrets in production secrets manager.
2. Deploy Redis + Celery worker and run E2E with `USE_CELERY=true`.
3. Configure daily backups to S3/MinIO and perform a restore drill.
4. Obtain sandbox credentials for Salla/Zid/Foodics/Qoyod and validate connectors.
5. Commission a penetration test and begin ISO 27001 gap assessment.
6. Launch the 20-merchant Riyadh pilot to generate real case studies.
