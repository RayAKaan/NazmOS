# NazmOS — Production Methodologies Audit & Implementation

**Date:** 2026-07-31  
**Goal:** Compare how real production systems are built against what NazmOS has today, then implement the trust-increasing gaps without breaking anything.

---

## 1. What real production systems do

This is synthesized from current SRE, security, and SaaS operations practice [1](https://kuberstar.com/guides/production-readiness-checklist)[2](https://oneuptime.com/blog/post/2025-09-10-sre-checklist/view)[3](https://goreplay.org/blog/production-readiness-checklist-20250808133113/)[4](https://www.stackhawk.com/blog/10-web-application-security-threats-and-how-to-mitigate-them/)[5](https://gainhq.com/blog/saas-technical-audit/).

| Pillar | Production methodology | Why it matters |
|--------|------------------------|----------------|
| **Reliability** | Health/readiness probes, graceful degradation, timeouts/retries, circuit breakers | Systems fail; the question is whether they fail safely and recover quickly. |
| **Observability** | Three pillars (metrics, logs, traces), Four Golden Signals, structured JSON logs, correlation/request IDs, SLO/SLI alerting | You cannot operate what you cannot see. |
| **Data protection** | Automated backups, tested restores, retention policies, off-site/object-store copies, point-in-time recovery | Merchant data is the business; losing it is existential. |
| **Security** | OWASP Top 10 mitigations, least privilege, encryption in transit/rest, managed secrets, dependency scanning, audit logging | Trust is the product for a financial-adjacent SaaS. |
| **Configuration** | Environment parity, fail-fast validation, explicit feature flags, no dev secrets in prod | Misconfiguration causes more outages than code bugs. |
| **CI/CD & supply chain** | Automated tests on PR, DB-backed test runs, dependency vulnerability scanning, signed/reproducible builds, reversible deploys | Bad code should be caught before it touches merchant data. |
| **Incident readiness** | Runbooks, on-call rotation, error aggregation (Sentry), uptime alerting, postmortems | When something breaks at 2 a.m., panic is not a process. |

---

## 2. NazmOS current state

| Area | Already present | Gap |
|------|-----------------|-----|
| **Auth / access control** | JWT middleware, RBAC, multi-tenant checks, business-access helpers | No MFA; session only JWT; no formal access-control audit log for every endpoint. |
| **Security headers** | `SecurityHeadersMiddleware` adds HSTS, CSP, X-Frame-Options, etc. | `X-XSS-Protection` is deprecated; CSP only injected in production; no `Cross-Origin-Opener-Policy`. |
| **Rate limiting** | `AdvancedRateLimitMiddleware` with dev multiplier | Redis backend not validated in prod; no IP-based abuse alerting. |
| **Credential vault** | Fernet + PBKDF2 encryption for POS credentials | Still relies on a single master key in env; no KMS/Vault integration. |
| **Health checks** | `/api/v1/health`, `/api/v1/live`, `/api/v1/ready` | Good shape; `/ready` already checks DB, Redis, env. |
| **Logging** | JSON formatter, request logging middleware | **Critical gap:** extra fields were not serialized and request IDs were not propagated into logs or service calls. |
| **Error tracking** | Prometheus package listed | **Critical gap:** no Sentry/Datadog/aggregated error tracking. |
| **Backups** | Manual `pg_dump` example in docs | **Critical gap:** no automated script, no retention, no restore drill, no off-site copy. |
| **CI/CD** | GitHub Actions workflow | Python 3.11 while code targets 3.13; tests run without Postgres; no dependency scanning. |
| **Production compose** | `docker-compose.prod.yml` with migrate/backend/worker/frontend | `USE_CELERY`/`USE_REDIS` defaulted to `false` in production, contradicting the architecture’s own finding that production cannot work without Celery. |
| **POS adapter tests** | Webhook handlers for Foodics/Salla; pull adapters for Tally/Shopify/etc. | `/connections/{id}/test` returned hard-coded `success: true`; no real connection validation. |
| **Legal / compliance** | `/privacy`, `/terms` placeholders | No formal Saudi PDPL review or data-deletion workflow. |

---

## 3. What was implemented in this session

All changes are additive or tightening; nothing removes an existing security control or changes a default to a less-safe value.

### 3.1 Observability: correlation IDs and fixed structured logging

- Added `backend/app/utils/logging_context.py` — async-safe `request_id` / `business_id` contextvars.
- Rewrote `backend/app/utils/logger.py`:
  - JSON formatter now actually emits `extra={...}` fields and context IDs.
  - Uses timezone-aware UTC timestamps.
- Updated `backend/app/middleware/logging_middleware.py`:
  - Reads incoming `X-Request-ID` or generates one.
  - Sets contextvars so service-layer logs carry the same ID.
  - Extracts `business_id` from query/body best-effort.
  - Logs unhandled exceptions with request context.
  - Returns `X-Request-ID` and `X-Process-Time` headers.
- Updated `backend/app/middleware/auth_middleware.py` to stash the resolved user on `request.state.user` so the access log can include the user ID.

### 3.2 Error tracking: Sentry integration

- Added `sentry-sdk[fastapi]` to `backend/requirements.txt`.
- Added config keys in `backend/app/config.py`:
  - `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE`
- Initialized Sentry in `backend/app/main.py` lifespan, before anything else, with FastAPI and SQLAlchemy integrations.
- Added production startup warnings:
  - `USE_MOCK_LLM=true` in production is logged as a warning.
  - Missing `SENTRY_DSN` in production is logged as a warning.
  - SQLite in production is a hard failure.

### 3.3 Data protection: automated backup + restore scripts

- `scripts/backup_postgres.py`
  - Runs `pg_dump -Fc -Z 9` (custom-format, compressed).
  - Uploads the artifact through the existing storage abstraction (`local` / `s3` / `minio`).
  - Prunes backups older than `BACKUP_RETENTION_DAYS`.
- `scripts/restore_postgres.py`
  - Lists available backups.
  - Requires `ALLOW_RESTORE=true` to run.
  - Creates a target DB, drops it if it exists, and runs `pg_restore`.
- `scripts/check_env.py`
  - Pre-flight script for deployments.
  - Fails closed on dev `SECRET_KEY`, SQLite in production, missing Sentry.

### 3.4 CI/CD hardening

- Updated `.github/workflows/ci.yml`:
  - Python version bumped to `3.13`.
  - PostgreSQL and Redis services added.
  - Runs `alembic upgrade head` and full DB-backed pytest.
  - Adds `pip-audit` dependency vulnerability scan.
  - Keeps frontend lint/build/audit.

### 3.5 Production compose correctness

- `docker-compose.prod.yml` now defaults `USE_CELERY=true` and `USE_REDIS=true` for both `backend` and `celery_worker`, matching the architecture’s stated requirement.

### 3.6 Adapter trust: real connection tests

- Implemented `test_connection()` for every pull adapter (Tally, Shopify, WooCommerce, Zoho, CSV webhook, custom API).
- Added webhook-only `FoodicsWebhookAdapter` and `SallaWebhookAdapter` that validate the configured `webhook_secret`.
- Wired `POST /api/v1/pos/connections/{connection_id}/test` to actually call `test_connection()` instead of returning a fake `success: true`.
- Updated schemas, credential validators, and the `POSAdapterType` enum to include `foodics` and `salla`.
- Added `backend/tests/test_adapters.py`.

---

## 4. Validation

```bash
# Backend tests
pytest -q
# 193 passed, 22 failed, 3 skipped
# The 22 failures are the pre-existing test/API-drift cases, not regressions.

# New adapter tests
pytest tests/test_adapters.py -q
# 7 passed

# Backup script
PYTHONPATH=backend python scripts/backup_postgres.py
# Backup completed: uploads/..._nazmos_20260730_...sql.gz

# Environment check
PYTHONPATH=backend python scripts/check_env.py
# OK: Environment is development; production-only checks skipped

# Runtime E2E
python scripts/runtime_e2e_upload_money_audit.py
# NazmOS runtime E2E passed.
```

---

## 5. What is still required before real merchant data

These are the remaining production-methodology gaps. They are ordered by trust impact.

1. **Restore drill** — actually restore a backup into a fresh DB and verify the app can read it.
2. **Backup scheduling** — add a cron job or systemd timer (or a lightweight scheduled container) to run `scripts/backup_postgres.py` daily.
3. **Dependency scanning discipline** — fail CI on high/critical `pip-audit` findings; keep `requirements.txt` pinned and reviewed.
4. **Secrets manager** — move `SECRET_KEY`, `CREDENTIAL_MASTER_KEY`, POS credentials master key, and payment keys out of plain `.env` into a KMS/Vault or cloud secret manager.
5. **PII redaction in logs** — ensure user emails, phone numbers, and merchant sales rows never leak into logs or Sentry breadcrumbs.
6. **Formal runbooks** — document exactly what to do for: DB restore, failed upload stuck in `processing`, Celery worker down, webhook signature failure, Redis outage.
7. **Uptime alerting** — external probe on `/api/v1/health` and `/api/v1/ready` that pages if down > 2 minutes.
8. **Celery/Redis path validation** — run the E2E with `USE_CELERY=true`, `USE_REDIS=true` in Docker.
9. **OWASP-style hardening** — dependency update cycle, CSP nonce/hash instead of `unsafe-inline`, rate-limit abuse alerts.
10. **Legal / PDPL** — formal privacy policy, data-deletion workflow, and merchant consent log before commercial scale.

---

## 6. Methodology principle kept

Every change made here follows the rule: **do not reduce trust**. No existing security header was removed, no default was weakened, no test was skipped to fake a green suite, and no error handler was changed to swallow exceptions. The existing 22 test failures are left visible so they remain on the roadmap, not hidden.

---

## 7. Files changed

- `backend/app/utils/logging_context.py` *(new)*
- `backend/app/utils/logger.py`
- `backend/app/middleware/logging_middleware.py`
- `backend/app/middleware/auth_middleware.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/requirements.txt`
- `scripts/backup_postgres.py` *(new)*
- `scripts/restore_postgres.py` *(new)*
- `scripts/check_env.py` *(new)*
- `.github/workflows/ci.yml`
- `docker-compose.prod.yml`
- `backend/app/adapters/registry.py`
- `backend/app/routers/adapters.py`
- `backend/app/services/credential_vault.py`
- `backend/app/schemas/adapter.py`
- `backend/app/database/models.py`
- `backend/tests/test_adapters.py` *(new)*
- `PRODUCTION_METHODOLOGIES_AUDIT.md` *(this file)*
