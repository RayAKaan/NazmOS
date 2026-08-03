# NazmOS API Changelog

All notable changes to the NazmOS API are documented in this file.

## [2.1.0-ksa] - 2026-08-03

### Security
- Replaced `python-jose` with PyJWT to remove high/critical CVEs.
- Added PostgreSQL Row-Level Security (RLS) with tenant-isolation policies on
  29 business-scoped tables.
- Added restricted `nazmos_app` database role for production RLS enforcement.
- Added idempotency-key middleware for safe retries of POST/PATCH/PUT requests.

### Observability
- Added PII redaction to JSON logs (passwords, tokens, emails, phones, etc.).
- Added Prometheus `/metrics` endpoint and request latency/counter metrics.
- Added production runbooks under `docs/runbooks.md`.

### DevOps
- Hardened CI to block high/critical CVEs from `pip-audit`.
- Bumped CI PostgreSQL service from 15 to 17.
- Added backend runtime E2E smoke tests to CI.
- Added `X-NazmOS-API-Version` response header.

### Fixed
- Fixed forecast cache insert to include `id` and avoid `NotNullViolation`.
- Rewrote legacy skipped tests against current API shapes.

## [2.0.0-ksa] - 2026-07-30

### Added
- NazmOS Retail Recovery API: Money Audits, stockout prevention, WhatsApp
  approvals, and Recovery Match preview.
- FastAPI backend with async SQLAlchemy 2.0 and PostgreSQL 17.
- Next.js 16 + React 18 frontend.
- OpenRouter gateway for LLM routing.
