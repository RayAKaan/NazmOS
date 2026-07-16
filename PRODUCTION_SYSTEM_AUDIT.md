# NazmOS Production System Design Audit

Date: 2026-07-15
Audited workspace: `/home/user/NazmOS_latest`

## Executive verdict

NazmOS is now a strong **controlled production-pilot candidate**, not yet a fully mature SaaS platform.

Current production design grade:

```txt
Founder-led pilot architecture: 8/10
Controlled production v1 architecture: 7/10
Self-serve SaaS architecture: 5/10
Enterprise architecture: 3/10
```

Bluntly:

```txt
Good enough to deploy for a small controlled pilot after real runtime E2E passes.
Not good enough yet for broad public self-serve launch.
```

## Intended production architecture

```txt
Browser / Merchant
    ↓
Next.js frontend
    ↓ HTTPS
FastAPI backend
    ↓
Postgres = source of truth
Redis = broker/cache/progress channel
Celery worker = file ingestion / background jobs
Local upload volume = pilot file store
OpenRouter = model gateway
WhatsApp = manual first, API later
```

## Core production services

### 1. Frontend

Technology:

```txt
Next.js 16.2.10
React 18
Standalone production output
```

Responsibilities:

```txt
Landing/product demo
Auth screens
Upload + mapping UX
Dashboard
Money Audit UI
Recovery Match UI
Pilot Ops UI
Privacy/Terms
```

Current status:

```txt
lint clean
build clean
npm production audit clean
```

### 2. Backend API

Technology:

```txt
FastAPI
SQLAlchemy async
Alembic migrations
Pydantic settings
```

Responsibilities:

```txt
Auth
Business bootstrap
Upload metadata
Column mapping
Dashboard APIs
Money Audit APIs
Recovery Match APIs
Pilot Ops console
Health/readiness
```

Current status:

```txt
124 backend tests passed
OpenAPI route sweep clean
frontend/backend contract clean
```

### 3. Postgres

Role:

```txt
source of truth
users
businesses
items
inventory
transactions
uploads
money audits
audit actions
recovery listings/matches
ops state
```

Production requirement:

```txt
managed Postgres or backed-up self-hosted Postgres
daily backups
restore test
migration gate before deploy
```

### 4. Redis

Role:

```txt
Celery broker/result backend
ETL progress pub/sub
cache fallback
rate-limit optional backend
```

Production requirement:

```txt
Redis persistence on
password protected
worker/backend same Redis URL
monitor memory and evictions
```

### 5. Celery worker

Role:

```txt
upload ingestion
forecast refresh
analytics summary rebuild
stale upload cleanup
```

Important audit finding:

```txt
Production cannot work without Celery.
```

The root production compose has now been corrected to include:

```txt
celery_worker
```

### 6. File storage

Current pilot design:

```txt
Docker volume mounted at /app/uploads
```

Acceptable for:

```txt
controlled pilot
single server
small merchant count
manual ops
```

Not enough for:

```txt
multi-server SaaS
large uploads
durable compliance-grade file retention
```

Next step before scale:

```txt
S3-compatible object storage
file retention policy
merchant deletion workflow
signed URLs for founder review
```

### 7. Model routing

Current design:

```txt
OpenRouter is the model gateway
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openrouter/auto
```

Good:

```txt
No direct hardcoded model-vendor API URL
Provider-neutral llm_usage_tokens
OpenRouter headers configured
Mock mode available for testing
```

Production advice:

```txt
Keep USE_MOCK_LLM=true for early pilot unless model output is actually needed.
Money Audit and Recovery Match should not depend on LLM correctness.
```

## Main production data flows

### Flow A: Free Money Audit

```txt
merchant registers/login
business bootstrap creates first store
merchant uploads sales file
backend validates file and detects columns
merchant confirms mapping
Celery imports rows
merchant uploads inventory file
Celery imports inventory snapshot
Money Audit generated
merchant/founder approves action
merchant/founder marks completed
Money Recovered updates
```

Status:

```txt
code path exists
no-DB tests pass
real runtime E2E script added
requires Postgres+Redis+Celery test after download
```

### Flow B: Recovery Match

```txt
inventory data exists
Recovery Match preview finds surplus
merchant creates listing
nearby buyer suggestions generated
buyer interested
both sides approve
contact reveal after mutual approval
completion/recovered value tracked
issue reporting available
```

Status:

```txt
manual pilot foundation exists
not marketplace-production ready
founder review SOP required
```

### Flow C: Ops console

```txt
founder opens /ops
sees uploads
failed imports
audit queue
pending actions
Recovery Match issues
operator next steps
```

Status:

```txt
basic pilot ops console exists
needs cross-merchant admin view later
```

## Production deployment design after fixes

Recommended local production-pilot stack:

```txt
docker-compose.prod.yml
```

Services:

```txt
postgres
redis
migrate
backend
celery_worker
frontend
```

Important improvements made:

```txt
migrate job runs alembic upgrade head
backend waits for migration success
celery worker waits for migration success
postgres/redis are not publicly exposed
backend/frontend bind to 127.0.0.1 for reverse proxy use
frontend API URL is PUBLIC_API_URL, not hardcoded localhost
OpenRouter env is propagated
shared upload volume used by backend and celery
```

## Critical production blockers still remaining

### Blocker 1: Real runtime E2E not run in this sandbox

Reason:

```txt
sandbox has no Docker/Postgres/Redis/psql
```

Required after download:

```bash
docker compose -f docker-compose.local.yml up --build
cd backend
alembic upgrade head
cd ..
python scripts/runtime_e2e_upload_money_audit.py
```

Pass condition:

```txt
sample sales file imports
sample inventory file imports
Money Audit generated
action approved
action completed
Money Recovered > 0
/ops returns pilot state
```

### Blocker 2: File storage is still local-volume only

Acceptable for pilot.
Not acceptable for scaled production.

Need before scale:

```txt
S3-compatible storage
file lifecycle policy
encrypted bucket
signed URL access
retention/deletion tooling
```

### Blocker 3: Legal is placeholder only

Current:

```txt
/privacy
/terms
pilot-grade placeholders
```

Need before real commercial scale:

```txt
Saudi legal review
PDPL review
data deletion terms
Recovery Match liability terms
merchant consent wording
```

### Blocker 4: Observability is minimal

Current:

```txt
health endpoints
logs
some prometheus package dependency
```

Need before production scale:

```txt
Sentry
uptime monitor
worker failure alerts
database backup alert
disk usage alert
upload failure alert
structured request IDs in logs
```

### Blocker 5: No backup/restore automation yet

Need:

```txt
daily pg_dump or managed backup
restore drill
backup retention policy
Redis persistence verification
upload volume backup or object storage
```

### Blocker 6: Multi-tenant/admin model is still pilot-grade

Current:

```txt
per-business owner/team model exists
/ops is business-scoped
```

Need later:

```txt
founder super-admin console across merchants
support impersonation audit log
merchant status pipeline
billing/support notes
```

## Security audit notes

Good:

```txt
SECRET_KEY validation in production
security headers middleware
rate limiter
password validation tests
prompt sanitizer tests
PII masking helpers
OpenRouter avoids direct model-vendor hardcoding
```

Still needs:

```txt
formal threat model
CSRF/session review if cookie auth added
S3 encryption/access design
production CORS set to real domains only
secrets manager, not .env on disk for scale
```

## Deployment sequence after download

### 1. Create production env

```bash
cp backend/.env.production.example backend/.env.production
python scripts/check_env.py backend/.env.production
```

The example file will fail validation because it contains placeholders. Your real env must pass.

### 2. Local runtime pilot test

```bash
docker compose -f docker-compose.local.yml up --build
cd backend
alembic upgrade head
cd ..
python scripts/runtime_e2e_upload_money_audit.py
```

### 3. Production-pilot deploy

```bash
docker compose -f docker-compose.prod.yml --env-file .env up --build -d
```

Then check:

```bash
curl https://YOUR_DOMAIN/health
curl https://YOUR_DOMAIN/api/v1/ready
```

### 4. First merchant test

Use:

```txt
sample_data/sales_history_sample.csv
sample_data/inventory_snapshot_sample.csv
```

Then use a real merchant file.

## Final production design verdict

### Ready now for

```txt
internal demo
merchant walkthrough
controlled founder-led pilot after runtime E2E passes
```

### Not ready yet for

```txt
public self-serve SaaS
large-scale multi-merchant marketplace
unattended Recovery Match
enterprise deployment
```

## Highest priority next actions

1. Run local Docker runtime E2E.
2. Fix any Celery/upload/import bugs found there.
3. Deploy to a single VPS behind Caddy/Nginx TLS.
4. Add Sentry and daily Postgres backup.
5. Run first real merchant files.
6. Produce first Money Recovered case study.

If local runtime E2E passes, NazmOS becomes production-pilot ready.
