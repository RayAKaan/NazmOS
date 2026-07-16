# NazmOS Download Package

This folder is cleaned for handoff/download.

## What is included

Core product source:

```txt
backend/                 FastAPI backend, Alembic migrations, Celery tasks
frontend/                Next.js frontend
sample_data/             Sample sales/inventory files for runtime tests
scripts/                 Verification and runtime smoke/E2E scripts
docs/                    Pilot SOP and preview HTML files
.github/workflows/       CI workflow
Makefile                 Common verification commands
docker-compose.yml       Local runtime stack alias
docker-compose.local.yml Local runtime stack
docker-compose.prod.yml  Production-pilot stack
```

Important reports:

```txt
TESTING_REPORT.md
PRODUCTION_READINESS.md
PRODUCTION_SYSTEM_AUDIT.md
```

## What was removed from the download

Generated artifacts/caches were removed:

```txt
node_modules
.next
__pycache__
.pytest_cache
build/dist/coverage artifacts
logs/tmp files
local upload temp dirs
```

## First commands after download

Install backend dependencies and run no-DB verification:

```bash
python scripts/verify_workspace.py
```

If dependencies are not installed yet:

```bash
cd backend
pip install -r requirements.txt
cd ../frontend
npm ci --ignore-scripts --no-audit --no-fund
cd ..
python scripts/verify_workspace.py
```

## Runtime pilot test

Requires Docker:

```bash
docker compose -f docker-compose.local.yml up --build
```

Then migrate and run sample-file E2E:

```bash
cd backend
alembic upgrade head
cd ..
python scripts/runtime_e2e_upload_money_audit.py
```

## Model router

NazmOS uses OpenRouter, not a hardcoded model provider.

Production env should use:

```env
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_SITE_URL=https://nazmak.com
OPENROUTER_APP_NAME=NazmOS by Nazmak
LLM_MODEL=openrouter/auto
```

## Current tested status

Last in-sandbox status:

```txt
Backend no-DB tests: 124 passed, 39 skipped, 0 failed
Frontend lint/build/audit: clean
OpenAPI route sweep: clean
Frontend/backend contract: clean
Production npm audit: 0 vulnerabilities
```

The skipped backend tests require real Postgres/Redis.
