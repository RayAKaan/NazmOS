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

## 8. PII / Personal Data Breach Response (PDPL)

### 8.1 Detection
1. Sentry or log alert flags exposure of email, phone, Saudi ID, or file contents.
2. Verify scope via `request_id` and affected `business_id`.

### 8.2 Containment (within 1 hour)
1. Rotate any exposed credentials (`SECRET_KEY`, `CREDENTIAL_MASTER_KEY`, webhook secrets).
2. Identify and patch the logging/code path that emitted PII.
3. Confirm redaction filters in `app/utils/logger.py` cover the exposed field.

### 8.3 Notification (within 72 hours)
1. Notify SDAIA per PDPL requirements.
2. Notify affected merchants with: what happened, what data, what we did, what they should do.
3. Record everything in the audit log.

### 8.4 Post-incident
1. Run a full PII scan across logs and Sentry payloads.
2. Update runbooks and add regression tests for the exposed field.
3. Review access controls and least-privilege policies.

## 9. Credential Master Key Rotation

1. Generate a new key: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Decrypt all POS connection credentials with the old key.
3. Re-encrypt with the new key and update `credentials_encrypted` in the database.
4. Update `CREDENTIAL_MASTER_KEY` in the secret store.
5. Rolling restart API and Celery workers.
6. Leave the old key available read-only until all workers have restarted.
