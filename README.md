# NazmOS Retail Recovery

**Find the cash trapped in your store.**

NazmOS is a Retail Recovery System for Saudi retailers — baqalas, supermarkets, cafes, restaurants, and retail shops. Send two exports (sales + inventory), and NazmOS finds the cash hiding in your business: dead stock, stockout risk, and margin leakage — then helps you recover it, with approvals over WhatsApp.

نظام استرداد تموزوس (نزموس) لقطاع التجزئة السعودي — أرسل ملفين فقط (المبيعات والمخزون)، وستجد نزموس السيولة النقدية المحبوسة في متجرك: بضائع راكدة، مخاطر نفاد مخزون، وتسريبات هامش ربح — ثم يساعدك على استردادها عبر واتساب.

---

## What NazmOS does

| Feature | What it means for your store |
|---|---|
| 🧾 **Free Money Audit** | Send sales + inventory exports → a full audit in 48 hours showing exactly where cash is trapped. |
| 📦 **Dead-stock detection** | Items sitting too long with no sales — cash you could free up today. |
| ⚠️ **Stockout risk** | Fast movers about to run out — lost sales you can prevent. |
| 💸 **Margin leakage** | Price, cost, and discount issues quietly eating your profit. |
| 📬 **Weekly Money Report** | A plain-language summary of what to fix next. |
| ✅ **WhatsApp approvals** | Approve recovery actions from your phone — no dashboard required. |
| 🤝 **Recovery Match preview** | Preview opportunities to match slow stock with nearby stores that can sell it. |

**The first wedge:** send two files — a sales export and an inventory export. NazmOS returns your Money Audit within 48 hours.

## How the loop works

```txt
Sales + inventory upload
        │
        ▼
   Money Audit
        │
        ▼
   Owner approves (WhatsApp / app)
        │
        ▼
   Action completed
        │
        ▼
   Money recovered
```

## API groups

NazmOS exposes **174 endpoints** across focused API groups. Interactive docs are live at `/docs` on any running backend; the full OpenAPI contract is committed at [`backend/docs/openapi.json`](backend/docs/openapi.json). Every response carries `X-NazmOS-API-Version: 2.1.0-ksa`.

| Group | Purpose | Key endpoints |
|---|---|---|
| Auth | Registration, login, sessions | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
| Businesses | Tenant bootstrap & context | `POST /api/v1/businesses/bootstrap`, `GET /api/v1/businesses/current` |
| Upload / ETL | Import messy CSV/XLS/XLSX | `POST /api/v1/upload/`, `POST /api/v1/upload/{id}/map`, `GET /api/v1/upload/{id}/status` |
| Money Audit | The core recovery loop | `POST /api/v1/money-audit/generate`, `POST .../actions/{id}/approve`, `POST .../actions/{id}/complete`, `GET .../whatsapp-summary` |
| Recovery Match | Nearby-store stock matching | `GET /api/v1/recovery-match/preview`, `GET /api/v1/recovery-match/matches`, `POST .../matches/{id}/reveal-contact` |
| Ops console | Founder/operator pilot console | `GET /api/v1/ops/pilot-console` (platform operator only) |
| Agent OS | Rule-based business agents | `POST /api/v1/agent/scan`, `GET /api/v1/agent/feed`, `POST /api/v1/agent/reason` |
| Intelligence | Reasoning, planning, memory, graphs | `POST /api/v1/intelligence/analyze`, `POST /api/v1/intelligence/plan`, `POST /api/v1/intelligence/simulate` |
| Pharmacy | Expiry / FEFO / SFDA vertical | `GET,POST /api/v1/pharmacy/lots`, `GET /api/v1/pharmacy/recalls` |
| POS webhooks | Foodics + Salla integrations | `POST /api/v1/pos/foodics/webhook`, `POST /api/v1/pos/salla/webhook` |
| WhatsApp | Approval bridge (mock $0 / live) | `GET,POST /api/v1/whatsapp/webhook`, `POST /api/v1/whatsapp/test-approve/{id}` |
| Partners | Accountants / Monshaat advisors | `POST /api/v1/partners/apply`, `GET /api/v1/partners/dashboard`, `GET /api/v1/partners/public` |
| Suppliers | Supplier network moat | `GET /api/v1/suppliers`, `GET /api/v1/suppliers/purchase-orders` |
| Compliance | GDPR / PDPL erasure & export | `GET /api/v1/compliance/export/{id}`, `DELETE /api/v1/compliance/delete/{id}` |
| Dashboard | KPIs, trends, alerts | `GET /api/v1/dashboard/summary`, `GET .../alerts`, `GET .../top-products` |
| Inventory | Stock, details, restock | `GET /api/v1/inventory`, `GET /api/v1/inventory/{id}/detail`, `POST /api/v1/inventory/restock` |
| Subscriptions / Billing | Plans, usage, checkout | `GET /api/v1/subscriptions/plans`, `POST /api/v1/subscriptions/checkout`, `GET /api/v1/subscriptions/usage` |
| Organizations | Multi-store chains & teams | `GET /api/v1/organizations/`, `GET .../chain/dashboard`, `POST .../team/invite` |
| Events | Event engine & subscriptions | `GET,POST /api/v1/events`, `POST /api/v1/events/batch` |
| Health & Ops | Health, readiness, metrics | `GET /api/v1/health`, `GET /api/v1/ready`, `GET /api/v1/live`, `GET /metrics` |

> Auth is required for all merchant endpoints; the ops console additionally requires the **platform-operator** identity (see [Security](#security-model)).

---

## Architecture

NazmOS is designed to run **at zero cost**: a single backend service with in-process background tasks and an optional client-side CSV parser. PostgreSQL, Redis, and Celery are optional upgrades — not requirements.

### Tech stack

**Backend**
- Python 3.13+, FastAPI, async SQLAlchemy 2.0, PostgreSQL 17
- Alembic migrations, Pydantic v2 / pydantic-settings, PyJWT
- LLM via **direct Groq + Google Gemini** providers (no gateway); `USE_MOCK_LLM=true` runs rule-based responses at $0 in development
- Optional: Redis, Celery, Prophet/scikit-learn for forecasting

**Frontend**
- Next.js 16 (App Router), React 18, TypeScript, Tailwind CSS
- Recharts, Zustand, React Hook Form + Zod, Framer Motion, PapaParse (client-side ETL)

### Zero-cost mode

| Setting | Default | Effect |
|---|---|---|
| `USE_CELERY` | `false` | Background tasks run in-process instead of a Celery worker |
| `USE_REDIS` | `false` | In-memory cache & rate limiting instead of Redis |
| `USE_CLIENT_ETL` | `false` | Server-side ETL; set `true` for browser-side CSV parsing |
| `USE_MOCK_LLM` | `true` | Rule-based LLM responses at $0 when no provider keys are set |

---

## Security model

- **JWT authentication** with refresh tokens and role-based access.
- **PostgreSQL Row-Level Security (RLS)** — tenant isolation policies across business-scoped tables, enforced via the restricted `nazmos_app` database role in production.
- **Capability-based authorization** — a single server-side capability model (see [`ACCESS_MODEL.md`](ACCESS_MODEL.md)) gates every route; the ops console is strictly **platform-operator** only (DB flag or `FOUNDER_EMAILS` allowlist).
- **Idempotency keys** for safe retries of POST/PATCH/PUT.
- **Credential vault** (AES) for POS integration secrets, plus **PII-redacted structured logs**.
- **Production fail-closed checks** on startup (secrets, Sentry, mock-LLM, SQLite).

---

## Quick start

### Option A — Zero-cost (SQLite, no Docker dependencies) ⭐

```bash
docker compose -f docker-compose.sqlite.yml up --build
```

- Backend: http://localhost:8000 · Docs: http://localhost:8000/docs

### Option B — Full local stack (Postgres 17 + Redis + Celery + frontend)

```bash
docker compose -f docker-compose.local.yml up --build
```

- Frontend: http://localhost:3000 · Backend: http://localhost:8000 · Flower: http://localhost:5555

### Option C — Manual backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit DATABASE_URL, SECRET_KEY, etc.
python -m alembic upgrade head
uvicorn app.main:app --reload
```

### Manual frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### Ops console access

The pilot console (`/ops`) requires the platform-operator identity. Set the allowlist in the backend environment:

```env
FOUNDER_EMAILS=founder@example.com
```

(Or set `is_platform_operator=true` on the user row in the database.)

---

## Environment variables (key ones)

Backend (`backend/.env`):

```env
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos
# SQLite: sqlite+aiosqlite:///./nazmos.db
SECRET_KEY=change-me-in-production-minimum-32-chars
CORS_ORIGINS=http://localhost:3000

# Zero-cost mode
USE_CELERY=false
USE_REDIS=false
USE_CLIENT_ETL=false

# LLM — direct providers, at least one key required in production
GROQ_API_KEY=
GOOGLE_AI_API_KEY=
LLM_PROVIDER_ORDER=groq,google,mock
USE_MOCK_LLM=true

# WhatsApp — mock ($0) or live
WHATSAPP_ENABLED=mock
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=

# Platform operator allowlist
FOUNDER_EMAILS=

# Production hardening
DATABASE_APP_ROLE=nazmos_app
CREDENTIAL_MASTER_KEY=
SENTRY_DSN=
METRICS_TOKEN=
```

Frontend (`frontend/.env.local`):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=NazmOS KSA
NEXT_PUBLIC_CURRENCY=SAR
NEXT_PUBLIC_LOCALE=ar-SA
NEXT_PUBLIC_CHAT_ENABLED=false
NEXT_PUBLIC_AGENT_ENABLED=true
```

See [`backend/.env.example`](backend/.env.example) and [`frontend/.env.example`](frontend/.env.example) for the full lists.

---

## Testing & CI

```bash
# Everything
make verify

# Backend unit + contract tests
make backend-test

# Frontend lint + build + audit
make frontend-test

# Retail Recovery contract test
make contract

# Runtime E2E (requires a running backend)
make runtime-e2e
```

CI (`.github/workflows/ci.yml`) runs: backend compile + `pip-audit` CVE gate, backend pytest against PostgreSQL, runtime E2E smoke tests, and frontend lint/build/audit/Jest/accessibility.

---

## Deployment & operations

- **Production-like local/staging**: `docker-compose.yml` (Postgres, Redis, API, Celery, nginx, Prometheus, Grafana).
- **Production compose**: `docker-compose.prod.yml`.
- **Terraform**: `infrastructure/terraform/` for cloud provisioning.
- **Backups**: `deployment/nazmos-backup.{service,timer}` + `scripts/backup_postgres.py`.
- **Runbooks**: [`RUNBOOKS.md`](RUNBOOKS.md) and [`docs/runbooks.md`](docs/runbooks.md).

---

## Project structure

```
NazmOS/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app + router registration
│   │   ├── config.py         # pydantic-settings
│   │   ├── routers/          # 30+ API routers (auth, money-audit, recovery-match, agent, …)
│   │   ├── services/         # Business logic (money_audit, recovery_match, etl, …)
│   │   ├── middleware/       # Auth, RLS, idempotency, rate limit, logging, metrics
│   │   ├── database/         # Models, connection, seeders
│   │   └── utils/            # Security, tracing, problem-details, OpenAPI helpers
│   ├── alembic/              # Migrations
│   ├── docs/openapi.json     # Committed OpenAPI golden (174 endpoints)
│   └── tests/                # Backend test suite
├── frontend/
│   └── src/app/(dashboard)/  # dashboard, inventory, upload, money-audit, recovery-match, ops, …
├── scripts/                  # E2E, smoke, backup/restore, demo-data generators
├── sample_data/              # Sample CSV exports for demos
├── infrastructure/terraform/ # Cloud provisioning
├── deployment/               # systemd backup units
└── docs/                     # Runbooks, pilot SOP
```

---

## Documentation index

| Doc | What it covers |
|---|---|
| [`README_KSA.md`](README_KSA.md) | KSA merchant pitch (Arabic market) |
| [`ACCESS_MODEL.md`](ACCESS_MODEL.md) | Capability & authorization model |
| [`docs/PILOT_SOP.md`](docs/PILOT_SOP.md) | Controlled-pilot operating procedure |
| [`RUNBOOKS.md`](RUNBOOKS.md), [`docs/runbooks.md`](docs/runbooks.md) | Production runbooks & ops |
| [`backend/docs/openapi.json`](backend/docs/openapi.json) | Full OpenAPI contract |
| [`CHANGELOG.md`](CHANGELOG.md) | API changelog |
| [`FRONTEND_PAGE_MAP.md`](FRONTEND_PAGE_MAP.md) | Frontend page ↔ endpoint map |

---

## License

Proprietary. © Nazmak. All rights reserved. This repository is not open-source and may not be copied, redistributed, or used commercially without written permission.
