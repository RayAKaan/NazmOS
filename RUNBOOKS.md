# NazmOS Operational Runbooks

## 1. Incident Response

### 1.1 Sev 1: API is down
1. Check `/health` on the load balancer and individual API instances.
2. Inspect Sentry for the latest uncaught exceptions.
3. Check Postgres and Redis health in monitoring dashboards.
4. If DB is saturated, scale `pool_size`/`max_overflow` via env vars and restart.
5. Roll back to last known good image if deploy caused it.

### 1.2 Sev 2: High 5xx rate
1. Look at `/metrics` or Grafana for error spikes by path.
2. Trace a sample failing request via `X-Request-ID` in logs.
3. Check Celery worker logs if failures correlate with background jobs.
4. Enable feature flag kill switch if a new module is misbehaving.

## 2. Database Failover

1. Promote read replica to primary (cloud-specific).
2. Update `DATABASE_URL` secret and restart API + workers.
3. Verify `/health/ready` returns `ready`.
4. Trigger a fresh backup from the new primary.

## 3. Celery Queue Backup

1. Check queue depths via Flower or Redis: `LLEN celery`.
2. If workers are stuck, inspect logs and restart worker containers.
3. For poison messages, move them to the `dead_letter` queue and fix the task.
4. Replay dead-letter events after the bug fix.

## 4. Rollback Procedure

1. Identify last good Git tag or image digest.
2. Redeploy: `git checkout <tag>` or `docker pull <image>:<tag>` and restart.
3. Run `alembic downgrade` only if the new migration was backward-compatible.
4. Verify E2E scripts pass.

## 5. Secret Rotation

### 5.1 SECRET_KEY
1. Generate new key: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Update secret store (Vault / AWS Secrets Manager / etc.).
3. Rolling restart API and Celery workers.

### 5.2 Database credentials
1. Rotate password in Postgres and secret store.
2. Update `DATABASE_URL` in secret store.
3. Rolling restart API and Celery workers.

### 5.3 Webhook secrets
1. Generate new secrets in Foodics/Salla dashboards.
2. Update `FOODICS_WEBHOOK_SECRET` / `SALLA_WEBHOOK_SECRET`.
3. Restart API. Old signatures will 401 until providers update.

## 6. GDPR / PDPL Deletion

1. Merchant requests deletion via app or support.
2. Endpoint `POST /api/v1/compliance/delete/{business_id}` schedules 30-day purge.
3. Audit log entry is created automatically.
4. After 30 days, run the purge worker or call `DELETE` with `immediate=true` for admin override.
5. Verify no business-scoped data remains via `GET /api/v1/compliance/export/{business_id}`.

## 7. Webhook Replay

1. Find event id from `webhook_events` table or ops console.
2. As admin/owner, call `POST /api/v1/pos/admin/webhooks/{event_id}/replay`.
3. Check that `status` becomes `processed` and downstream data is updated.
