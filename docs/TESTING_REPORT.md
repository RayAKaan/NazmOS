# NazmOS Test Pass Report

Date: 2026-07-15

## What was tested

### Backend

Commands run:

```bash
cd backend
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m compileall -q app tests
PYTHONPATH=. python -m alembic heads
PYTHONPATH=. python -m alembic history --verbose
```

Result:

```txt
118 passed
39 skipped
0 failed
```

Skipped tests are DB integration tests because this workspace has no local Postgres server on `localhost:5432` and no Docker/psql binary. The test fixture now skips DB integration tests cleanly instead of failing with connection errors.

### Backend module import and API route sweep

Imported all modules under `backend/app`:

```txt
98 modules checked
0 import failures
```

Generated OpenAPI and checked route prefixes:

```txt
99 API paths
0 double `/api/v1/api/v1` routes
/upload, /forecast, /decisions, /chat, /money-audit, /ops all exposed under /api/v1
```

ASGI smoke checks passed:

```txt
GET  /health -> 200
GET  /api/v1/health -> 200
GET  /api/v1/live -> 200
GET  /api/v1/ready -> 200 not_ready because this workspace has no DB/Redis
POST /api/v1/upload/ without auth -> 401
GET  /api/v1/money-audit/current without auth -> 401
```

### Migration graph

Alembic head:

```txt
006 (head)
```

Migration chain:

```txt
001 -> 002 -> 003 -> 004 -> 005 -> 006
```

Model/migration table coverage:

```txt
model tables: 44
missing model tables in migrations/runtime create-all coverage: none
```

### Frontend

Commands run:

```bash
cd frontend
npm run lint
npm run build
```

Result:

```txt
lint: passed with warnings
build: passed
```

Frontend build routes include:

```txt
/money-audit
/ops
/privacy
/terms
/upload
/recovery-match
/product-demo
```

### Product cleanup grep

Verified no active source references to removed legacy compliance, payroll, finance, charity-ledger, tax-invoicing, or optional retrieval-sidecar distractions.

Result:

```txt
no matches
```

## Issues found and fixed

### 0. Several routers were accidentally double-prefixed

Problem:

Some routers already had `/api/v1` in their own prefix but were also included in `main.py` with `prefix="/api/v1"`. This would expose broken paths such as a doubled API prefix and make frontend calls miss the backend.

Fix:

```txt
backend/app/main.py
```

Routers with full `/api/v1/...` prefixes are now included without an extra prefix. OpenAPI route audit now confirms:

```txt
0 double-prefixed API routes
```

### 1. Backend could not import locally because upload dir default was `/app/uploads`

Problem:

```txt
PermissionError: [Errno 13] Permission denied: '/app'
```

Fix:

```txt
backend/app/config.py
```

Changed default dev upload dir to:

```txt
uploads
```

Production can still override with `/var/nazmos/uploads` via env.

### 2. Frontend lint was interactive because ESLint config was missing

Fix:

```txt
frontend/.eslintrc.json
```

Added Next.js ESLint config.

### 3. Schema detector misclassified sales `Date` as `expiry_date`

Problem:

A sales file with:

```txt
Date, Product, Qty, Total, Cost
```

was treated as inventory because generic `Date` matched `expiry_date`.

Fix:

```txt
backend/app/services/schema_detector.py
```

Now generic date maps to:

```txt
transaction_at
```

Expiry date only maps when the column name contains expiry/expiration/best-before/Arabic expiry terms.

### 4. Schema detector misclassified sales `Qty` as `current_stock`

Fix:

```txt
backend/app/services/schema_detector.py
```

Now generic sales quantity maps to:

```txt
quantity
```

while stock/balance/on-hand columns still map to:

```txt
current_stock
```

### 5. Arabic cost column mapped as selling price

Problem:

```txt
سعر الشراء
```

could map to `unit_price` because it contains Arabic `سعر`.

Fix:

```txt
backend/app/services/schema_detector.py
```

Purchase/cost terms now map to:

```txt
cost_price
```

### 6. Legacy ETL/security tests were failing due missing compatibility APIs

Fixed compatibility without changing the product path:

```txt
SchemaDetector.detect_columns
SchemaDetector.get_confidence_scores
DataNormalizer wrapper class
ETLPipeline no-arg/process smoke API
DecisionEngine normalize/priority/confidence helpers
DatabaseManager facade
InventoryService facade
AuditService checkpoint helper
ChatMemory compatibility wrapper
```

### 7. Prompt sanitizer returned tuple where tests expected string

Fix:

```txt
backend/app/utils/prompt_sanitizer.py
```

Now:

```txt
sanitize(text) -> string
sanitize_with_flag(text) -> (string, suspicious_bool)
```

### 8. Security utilities hardened

Updated:

```txt
backend/app/utils/security_validators.py
```

Fixes:

```txt
command metacharacter neutralization
unquoted HTML event-handler removal
legacy PII masking aliases for old tests
password sequential-pattern tuning
```

### 9. Rate limiter compatibility and robustness

Updated:

```txt
backend/app/middleware/advanced_rate_limiter.py
```

Fixes:

```txt
robust mocked request header handling
compatibility helpers for rate-limit tests
```

### 10. Security headers compatibility

Updated:

```txt
backend/app/middleware/security_headers.py
```

Added:

```txt
set_default_headers
add_custom_headers
get_cors_config
```

### 11. Cache/LLM chaos resilience helpers

Updated:

```txt
backend/app/services/cache_service.py
backend/app/services/llm_orchestrator.py
```

Added/fixed:

```txt
cache failure returns None/False instead of crashing
memory pressure check
LLM fallback mode
rate-limit backoff
simple circuit-breaker counters
```

## Important limitation

This workspace cannot run true DB integration/migration tests because:

```txt
Docker: not installed
psql: not installed
Postgres server localhost:5432: not available
```

So this still must be run in a real dev/prod-like environment:

```bash
cd backend
alembic upgrade head
pytest -q
```

with Postgres + Redis available.

## Current testing verdict

```txt
Static/backend unit/security/chaos tests: passed
Frontend lint/build: passed
Module import sweep: passed
Migration graph: passed
Real DB integration: not executable in this workspace; cleanly skipped
Full runtime upload -> Celery -> Money Audit: still needs real stack test
```

---

## Additional deep API route sweep

After the first report, an OpenAPI-driven route sweep was added. It calls every generated API operation with dummy path/query/body values and no auth, then flags any exception or 5xx response.

Command summary:

```txt
Generated OpenAPI paths
Called every GET/POST/PUT/PATCH/DELETE operation via ASGITransport
Checked for exceptions and 5xx responses
Cleared in-memory rate limiter between paths to avoid false positives
```

Result after fixes:

```txt
111 operations tested
0 exceptions
0 server errors / 5xx
status distribution:
  401: 101
  422: 3
  200: 6
  403: 1
```

This is expected without an auth token and without Postgres/Redis. Protected routes correctly return `401`, malformed body routes return `422`, public health/plan/webhook routes return `200/403` as expected.

## New issues found and fixed in this sweep

### A. Tenant dependency bug in actions, organizations, and POS adapter routers

Problem:

Several routers had dependency functions like:

```py
def get_current_tenant(request) -> TenantContext:
```

Because `request` had no `Request` type annotation or `Depends`, FastAPI treated it as a normal string query parameter. Route calls crashed with:

```txt
AttributeError: 'str' object has no attribute 'state'
```

Affected routes included:

```txt
/api/v1/actions/*
/api/v1/organizations/*
/api/v1/pos/connections/*
```

Fix:

```txt
backend/app/routers/actions.py
backend/app/routers/organizations.py
backend/app/routers/adapters.py
```

The dependency now explicitly receives:

```py
request: Request
```

Result:

```txt
These routes now return 401 unauthenticated instead of crashing.
```

### B. WhatsApp dev test approval endpoint was exposed without auth

Problem:

```txt
POST /api/v1/whatsapp/test-approve/{action_id}
```

was unauthenticated and tried to hit the database even during no-DB smoke tests. In a workspace without Postgres it crashed.

Fix:

```txt
backend/app/routers/whatsapp.py
```

The endpoint now requires authenticated user dependency before attempting DB mutation. Without auth it returns:

```txt
401
```

instead of touching the DB.

## Latest backend result

```txt
118 passed
39 skipped
0 failed
```

## Latest frontend result

```txt
npm run lint  -> passed with warnings
npm run build -> passed
```

Warnings remaining:

```txt
React hook exhaustive-deps warnings in integrations/team/toast/i18n
Next.js 14.1.0 dependency warning from npm install
```

These are not current build blockers, but should be cleaned before public production.

## Latest file-detection smoke test

Sales file:

```txt
Date, Product, Qty, Total, Cost
```

Detected as:

```txt
sales_history
Date -> transaction_at
Product -> item_name
Qty -> quantity
Total -> total_amount
Cost -> cost_price
```

Arabic inventory file:

```txt
اسم المنتج, مخزون, سعر الشراء, باركود, تاريخ الصلاحية
```

Detected as:

```txt
inventory_snapshot
اسم المنتج -> item_name
مخزون -> current_stock
سعر الشراء -> cost_price
باركود -> barcode
تاريخ الصلاحية -> expiry_date
```

## Current hard blocker remains

This workspace still cannot run the true runtime test because it has no Postgres, Redis, Docker, or psql. The following still must be done in a real runtime environment:

```bash
cd backend
alembic upgrade head
pytest -q
```

Then a full product test:

```txt
register/login
upload sales file
upload inventory file
confirm mappings
Celery import
Money Audit generation
action approval
action completion
Money Recovered update
Pilot Ops console review
```

---

## Additional frontend/backend contract pass

A frontend API-call extractor was added to compare every `api.get/post/put/patch/delete` call in `frontend/src` against backend OpenAPI paths.

Initial result found broken frontend calls where pages manually included the API base prefix even though `frontend/src/lib/api.ts` already adds it.

Fixed files:

```txt
frontend/src/app/(dashboard)/chain/page.tsx
frontend/src/app/(dashboard)/integrations/page.tsx
frontend/src/app/(dashboard)/team/page.tsx
```

Final contract result:

```txt
frontend API calls: 50
missing backend contracts: 0
```

## Missing Team invitation endpoints fixed

The Team UI expected invitation list/resend routes, but backend only had invite/create and member update/remove routes.

Added backend routes:

```txt
GET  /api/v1/organizations/team/invitations
POST /api/v1/organizations/team/invitations/{invitation_id}/resend
```

Updated file:

```txt
backend/app/routers/organizations.py
```

## Additional API route sweep result

After all route fixes:

```txt
113 API operations tested
0 exceptions
0 server errors / 5xx
```

Expected unauthenticated distribution:

```txt
401: protected route
422: malformed auth/body request
200: public health/plans/webhook route
403: webhook verification without valid token
```

## Frontend dependency hardening

The frontend was upgraded from Next 14 to Next 16 after dependency audit found framework/dependency advisories.

Updated:

```txt
next: 16.2.10
eslint: 9.39.2
eslint-config-next: 16.2.10
postcss: 8.5.19
```

Added/updated:

```txt
frontend/eslint.config.mjs
frontend/next.config.js
frontend/package.json
frontend/package-lock.json
```

Next config cleanup:

```txt
removed deprecated swcMinify
replaced image domains with remotePatterns
removed custom _next/static cache header
```

Audit result:

```txt
npm audit --audit-level=moderate --omit=dev
found 0 vulnerabilities
```

Frontend final result:

```txt
npm run lint  -> passed, no warnings/errors
npm run build -> passed on Next 16.2.10
```

## Final current workspace test result

Backend:

```txt
118 passed
39 skipped
0 failed
```

Frontend:

```txt
lint: clean
build: clean
production dependency audit: clean
```

API contract:

```txt
OpenAPI route sweep: 113 operations, 0 failures
Frontend API contract: 50 calls, 0 missing backend routes
```

Still blocked by missing local services:

```txt
real Postgres migration execution
real Redis readiness
real Celery worker import execution
true upload -> database import -> Money Audit runtime flow
```

---

## Final pre-download hardening pass

### Added no-DB regression tests

Added:

```txt
backend/tests/test_retail_recovery_contract.py
```

Covers:

```txt
OpenAPI has no double /api/v1/api/v1 routes
frontend API calls match backend OpenAPI
sales file Date/Qty/Cost detection remains correct
Arabic inventory purchase-price detection remains correct
removed legacy/distraction terms are not reintroduced
```

Result:

```txt
5 passed
```

### Added sample merchant files

Added:

```txt
sample_data/sales_history_sample.csv
sample_data/inventory_snapshot_sample.csv
sample_data/arabic_inventory_sample.csv
```

Use these for first runtime upload/import testing once Postgres + Redis + Celery are running.

### Added verification scripts

Added:

```txt
scripts/verify_workspace.py
scripts/runtime_smoke.py
```

`verify_workspace.py` runs the no-DB workspace checks:

```txt
backend compile
backend pytest
alembic head check
OpenAPI/Frontend contract check
schema detector smoke check
frontend lint
frontend build
frontend production npm audit
```

`runtime_smoke.py` is for a real running deployment:

```bash
API_BASE_URL=http://localhost:8000 python scripts/runtime_smoke.py
ACCESS_TOKEN=... BUSINESS_ID=... python scripts/runtime_smoke.py
```

### Added pilot SOP

Added:

```txt
docs/PILOT_SOP.md
```

Covers:

```txt
merchant onboarding
allowed/excluded Recovery Match categories
manual WhatsApp approval SOP
Recovery Match v1 safety rules
pilot success criteria
```

### Frontend hardening

Upgraded and verified:

```txt
Next.js 16.2.10
ESLint 9.39.2
PostCSS 8.5.19 override
```

Final frontend result:

```txt
npm run lint  -> clean
npm run build -> clean
npm audit --audit-level=moderate --omit=dev -> 0 vulnerabilities
```

### Final backend result

After adding the new regression tests:

```txt
123 passed
39 skipped
0 failed
```

The 39 skipped tests require a real local Postgres test database and are intentionally skipped in this sandbox.

### Final API contract result

```txt
OpenAPI route sweep: 113 operations, 0 exceptions, 0 server errors
Frontend API contract: 50 calls, 0 missing backend routes
```

## Download readiness verdict

The workspace is now ready to download for runtime testing/deployment preparation.

What is proven here:

```txt
backend imports/compiles
backend non-DB tests pass
security/chaos tests pass
ETL/schema detector tests pass
OpenAPI routes do not crash unauthenticated
frontend builds cleanly
frontend/backend API contracts match
production frontend npm audit is clean
removed legacy/distraction terms are absent
```

What still requires your real machine/server:

```txt
Postgres alembic upgrade head
Redis readiness
Celery worker execution
actual upload -> import -> Money Audit with database data
```

---

## Final implementation additions before download

### Business bootstrap implemented

Problem found:

After registration there was no clean first-business/store bootstrap path, while dashboard code previously used a hardcoded demo UUID. That would break real first-merchant onboarding.

Added backend route:

```txt
POST /api/v1/businesses/bootstrap
GET  /api/v1/businesses/current
```

Files:

```txt
backend/app/routers/businesses.py
backend/app/routers/__init__.py
backend/app/main.py
frontend/src/app/(dashboard)/layout.tsx
```

Frontend dashboard layout now creates/loads the user's first business via the API instead of using a fake UUID.

### Local runtime stack added

Added:

```txt
docker-compose.local.yml
```

Services:

```txt
postgres
redis
backend
celery_worker
frontend
```

Purpose: run the real upload/import/Money Audit path after download.

### Runtime E2E upload/Money Audit script added

Added:

```txt
scripts/runtime_e2e_upload_money_audit.py
```

Flow:

```txt
health check
register or login test user
bootstrap business
upload sales sample
upload inventory sample
confirm mappings
poll Celery import status
generate Money Audit
approve first action
complete first action
check Pilot Ops console
```

Run after local stack is up and migrated:

```bash
docker compose -f docker-compose.local.yml up --build
cd backend && alembic upgrade head
cd ..
python scripts/runtime_e2e_upload_money_audit.py
```

### Environment validator added

Added:

```txt
scripts/check_env.py
```

It validates a real env file for required production keys and placeholder secrets.

Example:

```bash
python scripts/check_env.py backend/.env.production
```

Note: it is expected to fail on `.env.production.example` because that file deliberately contains placeholders.

### Makefile added

Added:

```txt
Makefile
```

Useful commands:

```bash
make verify
make backend-test
make frontend-test
make contract
make runtime-smoke
make runtime-e2e
make local-up
make local-down
```

### GitHub Actions CI added

Added:

```txt
.github/workflows/ci.yml
```

Jobs:

```txt
backend no-DB tests
frontend lint/build/audit
```

CI uses Python 3.11 because current backend requirement pins are safer on 3.11-era scientific packages.

### Final added regression state

```txt
backend/tests/test_retail_recovery_contract.py -> 5 passed
full backend no-DB suite -> 123 passed, 39 skipped, 0 failed
frontend lint/build/audit -> clean
```


---

## OpenRouter model-router migration

NazmOS no longer hardcodes the model provider API URL/key. The backend now uses OpenRouter as the model router.

Changed:

```txt
backend/app/config.py
backend/app/services/llm_orchestrator.py
backend/app/middleware/security_headers.py
backend/nginx/nginx.conf
backend/.env.example
backend/.env.production.example
backend/requirements.txt
backend/alembic/versions/007_llm_router_usage.py
```

New environment keys:

```txt
OPENROUTER_API_KEY
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_SITE_URL
OPENROUTER_APP_NAME
LLM_MODEL=openrouter/auto
```

The LLM service now calls:

```txt
{OPENROUTER_BASE_URL}/chat/completions
```

and sends OpenRouter ranking headers:

```txt
HTTP-Referer
X-Title
```

Provider-specific usage naming was replaced with:

```txt
businesses.llm_usage_tokens
```

New migration head:

```txt
007
```

OpenRouter regression test added in:

```txt
backend/tests/test_retail_recovery_contract.py
```

Final backend result after OpenRouter migration:

```txt
124 passed
39 skipped
0 failed
```

Final API route sweep after OpenRouter + business bootstrap:

```txt
115 operations
0 exceptions
0 server errors / 5xx
```

Final frontend result remains:

```txt
lint clean
build clean
production dependency audit clean
```
