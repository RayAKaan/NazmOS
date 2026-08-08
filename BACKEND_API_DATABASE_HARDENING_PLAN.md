# NazmOS Backend / API / Database Production-Hardening Plan

This plan applies the same systematic, checklist-driven approach we used for the frontend polish. Every item is concrete, production-grade, and avoids placeholders or TODOs.

Current baseline (from `PRODUCTION_HARDENING_REPORT.md`):
- 222 backend tests passing, 3 skipped (Prophet)
- `pip-audit`: 0 high/critical CVEs
- RLS enforced via `nazmos_app` role + middleware tenant context
- Prometheus `/metrics`, API version header + `CHANGELOG.md`, PII log redaction
- Celery/Redis runtime validation not solved locally (Redis not installed)
- Sentry DSN still empty
- GDPR/PDPL flows, webhook audit, staging/IaC not started

---

## Area 1 — Observability & Alerting (finish the gaps)

### Current state
- `LoggingMiddleware` emits per-request logs with request IDs and business IDs.
- `PrometheusMiddleware` exposes latency/counter metrics on `/metrics`.
- Sentry is wired in `lifespan` but `SENTRY_DSN` is empty in production.
- No distributed tracing (OpenTelemetry) or log correlation for Celery workers.

### What to do
1. **Require Sentry in production**
   - In `config.py`, raise `RuntimeError` when `ENVIRONMENT=production` and `SENTRY_DSN` is empty (same pattern already used for `SECRET_KEY`).
   - Add `SENTRY_DSN` to staging and production secret stores; rotate the DSN if it leaks.
2. **Structured JSON logging everywhere**
   - Convert all `logger.info(f"...")` and `print()` calls to structured extra fields.
   - Ensure Celery tasks use the same `setup_logger` and attach `task_id`, `business_id`, `task_name`.
3. **OpenTelemetry tracing**
   - Add `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`, `opentelemetry-instrumentation-celery`.
   - Export traces to Jaeger/Tempo or Sentry performance monitoring.
   - Propagate `traceparent` / `X-Request-ID` from frontend → API → worker.
4. **Alerts (Prometheus Alertmanager or Sentry)**
   - Alert on: 5xx rate > 1%, p95 latency > 2s, DB connection pool saturation, Celery queue depth > 100, failed uploads > threshold.

### Verification
- `SENTRY_DSN` populated and exceptions appear in Sentry project.
- `docker compose logs api` shows JSON lines with `request_id`, `business_id`, `method`, `path`, `status_code`.
- `/metrics` includes `nazmos_http_request_duration_seconds` and Celery task counters.

---

## Area 2 — API Contract Hardening

### Current state
- FastAPI auto-generates OpenAPI docs.
- `APIVersionMiddleware` injects version headers.
- Exception handlers return ad-hoc JSON shapes (`error`, `code`, `message`, `detail`, `timestamp`).

### What to do
1. **Adopt RFC 7807 Problem Details**
   - Replace custom error shapes with `{"type", "title", "status", "detail", "instance", "trace_id"}`.
   - Add `app/utils/problem_details.py` and a single `problem_response()` helper used by all exception handlers.
2. **Enrich OpenAPI/Swagger**
   - Add response schemas to every router (400, 401, 403, 422, 429, 500).
   - Tag endpoints consistently; add operation summaries.
   - Publish `/openapi.json` and freeze a versioned copy in CI for contract tests.
3. **API versioning policy**
   - Document deprecation lifecycle in `CHANGELOG.md`: announce at `vN`, sunset at `vN+2`.
   - Add `Sunset` header to deprecated endpoints.
4. **Request/response validation**
   - Upgrade to Pydantic v2 if not already; add `Field` descriptions and examples.
   - Add strict input sanitization for filenames, phone numbers, WhatsApp IDs.

### Verification
- `/docs` shows response models for every endpoint.
- Contract test compares current `/openapi.json` against the committed golden file and fails on drift.
- Error responses match RFC 7807 schema in all tests.

---

## Area 3 — Database Production Readiness

### Current state
- SQLAlchemy async engine with `pool_pre_ping`, `pool_size=10`, `max_overflow=20`.
- Alembic migrations exist; RLS policies are migration-driven.
- No documented index audit or backup/DR strategy.

### What to do
1. **Connection pool tuning**
   - Make `pool_size`, `max_overflow`, `pool_recycle` environment-driven (`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_RECYCLE`).
   - Set `pool_recycle=1800` to avoid stale connections behind proxies like PgBouncer.
2. **Index audit**
   - Add composite indexes on hot query paths: `business_id + created_at`, `business_id + sku`, `business_id + status`.
   - Add partial indexes for `status='pending_approval'` and `status='suggested'` to speed up feeds.
   - Add migration `alembic/versions/xxx_query_performance_indexes.py`.
3. **Backup & DR**
   - Daily `pg_dump` with `pg_basebackup` for point-in-time recovery.
   - Test restore monthly in a separate environment.
   - Encrypt backups at rest (S3 SSE-KMS or equivalent).
4. **Migration safety**
   - All migrations must be backward-compatible (add column → deploy → backfill → add constraint).
   - Add `alembic check` and migration lint to CI.
5. **Query N+1 audit**
   - Enable SQLAlchemy `echo=True` in staging; run E2E scripts; fix any N+1 with `selectinload` or joined queries.

### Verification
- `EXPLAIN ANALYZE` on top 10 API queries shows index usage.
- Restore drill passes in < RTO target.
- `alembic upgrade head` runs cleanly against a copy of production data.

---

## Area 4 — Async Worker Reliability

### Current state
- Celery app is conditionally created; stub used when `USE_CELERY=false`.
- Redis runtime validation not solved locally (Redis not installed).
- Beat schedule exists for forecasts, summaries, cleanup.

### What to do
1. **Install Redis locally and validate**
   - Add Redis service to `docker-compose.yml` and CI.
   - Add a startup probe that calls `celery_app.control.ping()` and fails closed if `USE_CELERY=true` but broker unreachable.
2. **Dead-letter queue + retries**
   - Configure `task_default_queue`, `task_routes`, and a `dead_letter` queue.
   - Add `autoretry_for=(Exception,)` with `max_retries=3` and exponential backoff for ingestion/forecast tasks.
3. **Worker monitoring**
   - Expose Celery metrics via `celery-prometheus-exporter` or flower.
   - Add `/health/ready` check that verifies broker and backend connectivity.
4. **Task idempotency**
   - Use the existing `idempotency_keys` table; require `idempotency_key` for all background tasks triggered from user actions.
5. **Timezone fix**
   - Celery timezone is currently `Asia/Kolkata`; change to `Asia/Riyadh` for KSA operations.

### Verification
- `docker compose up redis celery_worker` starts and processes a test task.
- `pytest tests/celery/` passes (add tests for retry, DLQ, idempotency).
- `/health/ready` returns `ready` when Redis/Celery are healthy.

---

## Area 5 — Security Hardening

### Current state
- Security headers middleware, rate limiter, RBAC, RLS, idempotency middleware.
- `SECRET_KEY` validation in production.
- CORS is configured but `allow_origins` comes from a comma-split string and `allow_methods=["*"]`.

### What to do
1. **Lock down CORS**
   - Reject wildcard origins in production; validate `CORS_ORIGINS` against an allow-list regex (`https://*.nazm.ai`, `https://app.nazm.ai`).
   - Restrict methods to `GET, POST, PUT, PATCH, DELETE`.
2. **Rate limits per tenant + endpoint**
   - Extend `AdvancedRateLimitMiddleware` to use `business_id` or `user_id` as the bucket key.
   - Lower limits for auth endpoints; higher for read-heavy dashboard endpoints.
3. **Secrets management**
   - Move all secrets (`SECRET_KEY`, `WHATSAPP_APP_SECRET`, webhook secrets, `OPENROUTER_API_KEY`, DB credentials) out of `.env` files in production.
   - Use AWS Secrets Manager / GCP Secret Manager / HashiCorp Vault with rotation every 90 days.
4. **Authorization audit**
   - Add automated tests that prove a user from business A cannot read business B's data even when RLS is bypassed.
   - Add `for update` row locks on money-critical operations (recovery match, action approvals).
5. **API input hardening**
   - Add maximum pagination limits (e.g., `limit <= 100`).
   - Validate file types by content magic bytes, not just extension.
   - Add rate-limiting and CAPTCHA-like slowdown on login/register.

### Verification
- `pytest tests/security/` covers RBAC, RLS bypass, CORS rejection, rate limiting.
- Production CORS config rejects `https://evil.example.com`.
- Secret rotation does not require code deploy (only secret store update + restart).

---

## Area 6 — Compliance & Data Governance

### Current state
- Privacy/terms pages exist on frontend.
- PII log redaction middleware exists.
- GDPR/PDPL data-deletion and retention flows not started.

### What to do
1. **Data inventory & classification**
   - Tag DB columns as PII (email, phone, full_name), sensitive (cost_price, supplier_phone), or business data.
   - Add a `data_classification` table or model annotations.
2. **GDPR/PDPL deletion endpoint**
   - Implement `POST /api/v1/compliance/account/delete` (hard delete after 30-day grace) and `GET /api/v1/compliance/export` (JSON data portability).
   - Cascade deletion must cover users, businesses, uploads, inventory, actions, recovery match data.
3. **Retention policies**
   - Automated purge of raw upload files after 90 days.
   - Anonymize old audit logs after 2 years.
   - Add `retention_policy` column per business tier.
4. **Consent log**
   - Store timestamped consent records for WhatsApp messaging and Recovery Match opt-in.
5. **Audit log table**
   - Append-only table: `actor_id`, `business_id`, `action`, `resource_type`, `resource_id`, `changes`, `ip_address`, `timestamp`.
   - Cover auth events, data exports, deletion requests, role changes.

### Verification
- Deletion E2E test: request → grace period → verify no user/business data remains.
- `pytest tests/compliance/` covers export, deletion, retention, consent.
- Audit log query returns all admin actions in last 90 days in < 500ms.

---

## Area 7 — Webhook Reliability & Audit

### Current state
- POS webhook routers exist for Foodics/Salla.
- Webhook secrets are configured but signature verification logic needs audit.

### What to do
1. **HMAC signature verification**
   - Verify `X-Hub-Signature-256` (Meta/Foodics/Salla) using constant-time comparison.
   - Reject webhooks with missing/invalid signatures with 401 and log attempt.
2. **Idempotency + deduplication**
   - Use `idempotency_keys` for webhook event IDs; return 200 for duplicates.
3. **Retry-friendly response**
   - Return `200 OK` only after successful persistence; return `500` only on transient errors so the provider retries.
4. **Webhook audit log**
   - Store `webhook_events` table: `provider`, `event_id`, `event_type`, `signature_valid`, `payload_hash`, `status`, `processed_at`, `error`.
5. **Replay endpoint**
   - Add `POST /api/v1/admin/webhooks/{event_id}/replay` for ops, gated to admin role.

### Verification
- `pytest tests/webhooks/` includes signature-verification success/failure, duplicate rejection, replay.
- Failed signature attempts are logged and do not process business logic.
- Webhook audit UI/API available for founder ops console.

---

## Area 8 — Testing & Quality Gates

### Current state
- 222 tests passing; E2E scripts for upload/money audit and KSA retail demo.
- No contract tests or load tests mentioned.

### What to do
1. **Contract tests**
   - Commit a golden `openapi.json` and fail CI if it drifts.
   - Add `schemathesis` or `hypothesis` property tests for critical endpoints.
2. **Integration coverage gaps**
   - Add tests for Recovery Match full lifecycle, WhatsApp approval flow, multi-branch orchestrator, supplier network.
3. **Load testing**
   - Add `locustfile.py` or `k6` script targeting `/api/v1/dashboard`, `/api/v1/upload`, `/api/v1/agent/feed`.
   - Run in CI with small load to catch regressions.
4. **Chaos / fault injection**
   - Test DB failure (fail closed), Redis failure (graceful degraded mode), Celery worker death (DLQ).
5. **Coverage gate**
   - Enforce `pytest --cov` threshold (start at 75%, target 85%).

### Verification
- CI runs unit + integration + contract + smoke load tests.
- Coverage report blocks PRs below threshold.
- E2E scripts run against staging before deploy.

---

## Area 9 — CI/CD & Staging Infrastructure

### Current state
- CI uses Postgres 17 + E2E wiring.
- Staging/IaC not started.

### What to do
1. **Docker Compose production-like stack**
   - `docker-compose.yml` with API, Celery worker, Celery beat, Redis, Postgres, nginx, Prometheus, Grafana.
   - Separate `docker-compose.override.yml` for local dev.
2. **Infrastructure as Code**
   - Terraform/Pulumi modules for KSA region (or chosen cloud): VPC, ECS/Cloud Run/GKE, RDS/Cloud SQL, ElastiCache/Memorystore, S3/MinIO, ALB, WAF.
   - Store state remotely with locking.
3. **GitHub Actions / CI pipeline**
   - Lint → test → build image → push to registry → deploy to staging → E2E → deploy to prod (manual gate).
   - Use semantic versioning and tag-based deploys.
4. **Environment parity**
   - Staging mirrors prod: same DB version, Redis, feature flags, secrets structure.
   - Use `ENVIRONMENT=staging` with real (small) TLS certs.
5. **Blue/green or canary deploy**
   - Start with rolling deploy + health checks; add traffic splitting later.

### Verification
- `terraform plan` succeeds with no drift.
- Staging URL (`https://staging.app.nazm.ai`) returns 200 on `/health`.
- E2E script passes against staging before every production deploy.

---

## Area 10 — Operational Runbooks & Documentation

### Current state
- `CHANGELOG.md` exists.
- `PRODUCTION_HARDENING_REPORT.md` exists.

### What to do
1. **API documentation**
   - Publish public API docs at `https://docs.nazm.ai` or `https://app.nazm.ai/api/docs`.
   - Add authentication guide, rate-limit behavior, webhook setup for Foodics/Salla.
2. **Runbooks**
   - `RUNBOOKS.md`: incident response, database failover, Celery queue backup, rollback procedure, secret rotation.
3. **On-call alerts**
   - PagerDuty/OpsGenie integration from Sentry/Prometheus.
4. **Dependency refresh policy**
   - Monthly `pip-audit` + `pip-compile` refresh; automated Dependabot-style PRs.

### Verification
- New engineer can follow runbook to rotate DB credentials and redeploy without asking.
- API docs are reachable and contain every public endpoint.

---

## Recommended execution order

| Phase | Areas | Rationale |
|-------|-------|-----------|
| Week 1 | 1, 4, 5 | Observability, Celery/Redis, security are foundational and unblock safe deploys. |
| Week 2 | 2, 3, 8 | API contracts, DB indexes, testing gates reduce regressions. |
| Week 3 | 6, 7 | Compliance and webhook audit are required for merchant trust and legal sign-off. |
| Week 4 | 9, 10 | Staging/IaC and runbooks make the team deploy-and-operate confidently. |

This mirrors the frontend approach: **fix the visible production gaps first, then harden the invisible infrastructure, and end with verification checklists that prevent regression.**
