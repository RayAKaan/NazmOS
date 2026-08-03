# NazmOS Production Runbooks

## 1. Health & Availability

### /health endpoint
```bash
curl https://<api>/health
```
Expected:
```json
{"status":"healthy","service":"nazmos-api","checks":{"database":"ok","redis":"ok"}}
```

### /ready endpoint (Kubernetes readiness)
```bash
curl https://<api>/ready
```

### /live endpoint (liveness)
```bash
curl https://<api>/live
```

## 2. Metrics & Alerting

Prometheus metrics are exposed at `/metrics` when `PROMETHEUS_ENABLED=true`.

Key metric names:
- `nazmos_http_requests_total` — request counter by method/path/status
- `nazmos_http_request_duration_seconds` — latency histogram
- `process_*` / `python_*` — standard process metrics

Recommended alerts:
- Error rate > 1% for 5m: `rate(nazmos_http_requests_total{status_code=~"5.."}[5m]) / rate(nazmos_http_requests_total[5m]) > 0.01`
- P95 latency > 2s for 5m
- Database check != "ok"

## 3. PII & Logging

All logs are JSON and PII-redacted before emission. Redacted fields include:
`password`, `password_hash`, `email`, `phone`, `token`, `api_key`, `secret`,
`credit_card`, `iban`, `credentials_encrypted`, `cr_number`, `wasfaty_id`.

Never log raw request bodies without running them through `redact_pii()`.

## 4. Row-Level Security (RLS)

In production set:
```bash
DATABASE_APP_ROLE=nazmos_app
```

The app connects as the table owner and issues:
```sql
SET LOCAL app.current_tenant_id = '<business_id>';
SET LOCAL ROLE "nazmos_app";
```

Verify RLS is active:
```sql
SELECT relname, relrowsecurity FROM pg_class WHERE relrowsecurity = true;
```

## 5. Dependency CVEs

Run locally:
```bash
pip-audit --desc -r backend/requirements.txt
```

CI blocks high/critical CVEs. Starlette informational advisories without a
severity rating do not fail the gate.

## 6. Rollback

Database: Alembic downgrade one revision:
```bash
alembic downgrade -1
```

Application: redeploy previous container image; config changes are env-var based.

## 7. On-Call Escalation

1. Check `/health` and `/metrics`.
2. Inspect recent logs for `level=ERROR` and `exception` fields.
3. If Sentry is configured (`SENTRY_DSN`), review unresolved issues.
4. Verify Postgres and Redis connectivity from the running pod.
5. For suspected RLS bypass, confirm `DATABASE_APP_ROLE` is set and the
   `nazmos_app` role exists with table grants.
