# NazmOS Production Readiness Runbook

NazmOS is now closer to a controlled production pilot because the core flow is explicit:

```txt
Upload sales/inventory files -> confirm columns -> generate Money Audit -> approve actions -> track recovered cash
```

## New production-facing pieces

### Money Audit

Backend:

```txt
backend/app/services/money_audit_service.py
backend/app/routers/money_audit.py
backend/alembic/versions/006_money_audit.py
```

Frontend:

```txt
frontend/src/app/(dashboard)/money-audit/page.tsx
```

Main endpoints:

```txt
GET  /api/v1/money-audit/current?business_id=...
POST /api/v1/money-audit/generate
GET  /api/v1/money-audit/{audit_id}
GET  /api/v1/money-audit/{audit_id}/whatsapp-summary
GET  /api/v1/money-audit/{audit_id}/print
POST /api/v1/money-audit/actions/{action_id}/approve
POST /api/v1/money-audit/actions/{action_id}/reject
POST /api/v1/money-audit/actions/{action_id}/complete
```

### Pilot Ops Console

Backend:

```txt
backend/app/routers/ops.py
```

Frontend:

```txt
frontend/src/app/(dashboard)/ops/page.tsx
```

Endpoint:

```txt
GET /api/v1/ops/pilot-console?business_id=...
```

Shows:

```txt
recent uploads
failed imports
latest Money Audit
pending recovery actions
Recovery Match issues
operator next steps
```

### Production health checks

```txt
GET /api/v1/live
GET /api/v1/ready
```

`/ready` checks database, Redis, required environment configuration, and reports degraded/not_ready states.

### Legal baseline pages

```txt
/privacy
/terms
```

These are pilot-grade placeholders. Get formal legal review before public launch.

## Required checks before taking real merchant data

Run from clean database:

```bash
cd backend
alembic upgrade head
```

Run backend tests:

```bash
pytest -q
```

Run frontend build:

```bash
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm run build
```

Start full runtime stack:

```txt
Postgres
Redis
Backend API
Celery ingestion worker
Frontend
```

Then test the full flow:

```txt
1. register/login
2. upload sales file
3. confirm mapping
4. import
5. upload inventory file
6. confirm mapping
7. import
8. open Money Audit
9. approve one action
10. mark one action completed
11. check Pilot Ops console
```

## Production v1 definition

NazmOS is production-ready v1 when this works without database manual fixes:

```txt
A Saudi retailer can create an account,
upload sales + inventory files,
confirm columns,
receive a Money Audit,
approve at least one recovery action,
and see Money Recovered tracked.
```

Plus:

```txt
If something fails, the founder can see it in Pilot Ops and recover safely.
```

## Still not done

These are still required before wider production:

```txt
clean Postgres migration test
real Celery/Redis import test
10+ real merchant file tests
formal legal review
proper file retention/deletion policy
S3-compatible file storage
Sentry or equivalent error tracking
daily database backups
production deployment smoke test
WhatsApp Business API or explicit manual send SOP
Recovery Match founder-review contact reveal SOP
```
