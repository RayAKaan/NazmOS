# NazmOS Retail Recovery

[![CI](https://github.com/RayAKaan/NazmOS/actions/workflows/ci.yml/badge.svg)](https://github.com/RayAKaan/NazmOS/actions/workflows/ci.yml)

**Find the cash trapped in your store.**

NazmOS is a Retail Recovery System for Saudi retailers — baqalas, supermarkets, cafes, restaurants, and retail shops. Send two exports (sales + inventory), and NazmOS finds the cash hiding in your business: dead stock, stockout risk, and margin leakage — then helps you recover it, with approvals over WhatsApp.

نظام استرداد تموزوس (نزموس) لقطاع التجزئة السعودي — أرسل ملفين فقط (المبيعات والمخزون)، وستجد نزموس السيولة النقدية المحبوسة في متجرك: بضائع راكدة، مخاطر نفاد مخزون، وتسريبات هامش ربح — ثم يساعدك على استردادها عبر واتساب.

---

## Table of contents

1. [What NazmOS does](#what-nazmos-does)
2. [How the recovery loop works](#how-the-recovery-loop-works)
3. [Who it's for](#who-its-for)
4. [Architecture overview](#architecture-overview)
5. [Zero-cost mode](#zero-cost-mode)
6. [Backend subsystems](#backend-subsystems)
7. [API surface](#api-surface)
8. [Security model](#security-model)
9. [Data model](#data-model)
10. [Frontend](#frontend)
11. [Quick start](#quick-start)
12. [LLM providers](#llm-providers)
13. [WhatsApp approvals](#whatsapp-approvals)
14. [Storage backends](#storage-backends)
15. [Background jobs (Celery)](#background-jobs-celery)
16. [Testing & CI](#testing--ci)
17. [Deployment & operations](#deployment--operations)
18. [Project structure](#project-structure)
19. [Documentation index](#documentation-index)
20. [Roadmap phases](#roadmap-phases)
21. [License](#license)

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

### What the money audit finds

Beyond the headline features, a NazmOS Money Audit combines several engines:

- **Dead-stock detection** — SKUs with no recent sales tied up as working capital.
- **Stockout-risk detection** — fast movers trending toward zero inventory before the next restock.
- **Margin leakage** — price below cost, cost inflation, discount erosion, and margin compared against a healthy baseline (financial-vocabulary normalization so `SmartWater 1.5L`, `smart water`, `SMARTWATER` all normalize to one SKU).
- **Recovery recommendations** — ranked, confidence-scored, IDR (impact/delay/risk)-weighted actions, each safely attributed to the audit that produced it.
- **AI reasoning** — optional LLM-driven explanation for *why* an item is a recommendation and *what* it would take to change that (see [`docs/RECOMMENDATION_ENGINE.md`](docs/RECOMMENDATION_ENGINE.md)).

---

## How the recovery loop works

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
   Impact logged → Money recovered (and the model learns)
```

Once an action is approved and completed, the **Impact Ledger** records the outcome and the **learning engine** feeds it back into the next audit — so recovery is a closed loop, not a one-off report.

### Guest audit (no sign-up)

Visitors can drop their two files at `/` and get an audit **without creating an account** (`POST /api/v1/guest-audit`). Signing up later merges the audit into their account and unlocks actions, WhatsApp approvals, and Recovery Match.

---

## Who it's for

NazmOS is built as a **multi-vertical retail recovery platform** with per-vertical feature gating:

| Vertical | Gate flag | What's enabled |
|---|---|---|
| General retail (default) | — | Full money audit, recovery match, agents |
| Pharmacy | `VERTICAL_PHARMACY=true` | Expiry / FEFO lot tracking, SFDA recall feeds, batch management |
| Food / F&B | `VERTICAL_FOOD=true` | Recipe / menu-level margin analysis |
| Auto parts | `VERTICAL_AUTO_PARTS=true` | Parts compatibility & cross-referencing |

---

## Architecture overview

NazmOS is designed to run **at zero cost**: a single backend service with in-process background tasks and an optional client-side CSV parser. PostgreSQL, Redis, and Celery are optional upgrades — not requirements.

```txt
┌──────────────────────────────────────────────────────────────────────────┐
│                                 Frontend                                  │
│   Next.js 16 (App Router) · React 18 · TS · Tailwind · Recharts · Zustand │
│   App routes  /dashboard /upload /money-audit /inventory /ops /chat …     │
└───────────────▲──────────────────────────────────────────────────────────┘
                │ HTTP/JSON (BFF proxy /api/v1/*) + RTL Arabic/English
┌───────────────┴──────────────────────────────────────────────────────────┐
│                                 Backend                                  │
│   FastAPI · async SQLAlchemy 2.0 · Pydantic v2 · Alembic · PyJWT          │
│                                                                            │
│   routers/  :  auth, businesses, upload, money_audit, recovery_match,     │
│               intelligence, agent, suppliers, pharmacy, partners, …       │
│   middleware:  auth (JWT), RLS tenant, RBAC capabilities, idempotency,    │
│               rate-limit, logging (PII-redacted), Prometheus, API-version │
│   services/ :  money_audit, etl, recovery_match, decision-engine,        │
│               learning-engine, knowledge-graph, event-engine, planning,   │
│               simulation, agent-runner, partner, billing, compliance …    │
│   LLM       :  direct Groq + Google Gemini (mock fallback at $0)          │
└───────▲──────────────────────┬────────────────────────┬───────────────────┘
        │                      │                        │
   PostgreSQL 17               Redis (optional)        Celery (optional)
   Alembic migrations          cache/rate-limit/       queues + beat
   Row-Level Security          broker                  (forecast, ingest,
   (nazmos_app role)                                   analytics, audit)
```

### Tech stack

**Backend**
- Python 3.13+, FastAPI, async SQLAlchemy 2.0, PostgreSQL 17
- Alembic migrations (`42` revision files), Pydantic v2 / pydantic-settings, PyJWT
- LLM via **direct Groq + Google Gemini** providers (no gateway dependency); `USE_MOCK_LLM=true` runs rule-based responses at $0 in development
- Optional: Redis (cache/broker/rate-limit), Celery (async queues + beat), Prophet/scikit-learn (forecasting/anomaly detection)
- OpenTelemetry tracing + Sentry error tracking + Prometheus `/metrics`

**Frontend**
- Next.js 16 (App Router `output: standalone`), React 18, TypeScript (strict), Tailwind CSS (OKLCH design-token driven)
- Recharts, Zustand, React Hook Form + Zod, Framer Motion, PapaParse (client-side ETL), lucide-react, shadcn/ui components
- i18n: Arabic (`ar`) and English (`en`), RTL-aware, defaults `ar-SA` / `SAR` / `Asia/Riyadh`
- PWA-ready service-worker registration, theme switching, reduced-motion support

### Zero-cost mode

| Setting | Default | Effect |
|---|---|---|
| `USE_CELERY` | `false` | Background tasks run in-process (FastAPI BackgroundTasks) instead of a Celery worker |
| `USE_REDIS` | `false` | In-memory cache & rate limiting instead of Redis |
| `USE_CLIENT_ETL` | `false` | Server-side ETL; set `true` for browser-side CSV parsing via PapaParse |
| `USE_MOCK_LLM` | `true` | Rule-based LLM responses at $0 when no provider keys are set |

> Setting `DATABASE_URL` to SQLite **automatically forces** `USE_CELERY=false` and `USE_REDIS=false`. In production, SQLite is rejected at startup (fail-closed).

---

## Backend subsystems

The backend is organized as focused routers backed by a large service layer. Principal subsystems:

### Money Audit & Recovery (`services/money_audit_service.py`, `recovery_intelligence.py`)
- ETL ingestion for messy CSV/XLS/XLSX (`etl_pipeline.py`, `schema_detector.py`, `data_normalizer.py`, `file_validator.py`).
- Audit generation, recommendation ranking (IDR/confidence), `findings`, and a reusable `AuditEngine` shared across money-audit, pharmacy, and partner paths.
- **Recovery Match** — find nearby stores willing to buy your slow stock, with consent-based contact reveal (`recovery_match_matcher.py`, `recovery_match_service.py`).

### Decision engine & safety (`decision_engine.py`, `ab_decision_framework.py`)
- Ranked, explainable decisions with decision logs (`intelligence_decisions`), outcome feedback, model-performance scoring, and phase-based learning loops.
- Execution guardrails (`execution_guard.py`, `constraint_service.py`, `autonomy_service.py`) so agents don't take irreversible actions above configured confidence thresholds (`AGENT_AUTO_MIN_CONFIDENCE`).

### Agent OS (`intelligence/agents/`, `app/routers/agent.py`)
Rule-based business agents covering **margin, pricing, inventory, procurement, recovery, finance, compliance, and suppliers**, run through a shared runner with a tool registry (`tool_registry.py`), observability (`agent_observability.py`), scan/feed/reason endpoints, and a `learning_engine` that improves policies from outcomes.

### Intelligence stack (`routers/intelligence.py`, `services/`)
- **Reasoning** — business-level reasoning with context builder and temporal reasoning.
- **Planning** — `nazm_planner.py` + `planning_engine.py` produce ranked plans.
- **Simulation** — `simulation_engine.py` + `v8_business_simulator.py` let you preview outcomes ("what if we discount item X?").
- **Knowledge graph** — entities, relationships, and event derivations.
- **Learning engine** — `learning_engine.py` / `learning_engine_advanced.py` / `outcome_learning.py`, with model-performance refresh and learning reconciliation.
- **Business memory** — persistent `business_memory` keyed by tenant + goal, updated via a debounced pipeline (`business_memory.py`, `branch_memory.py`, `product_memory.py`, `supplier_memory.py`).
- **Time machine** — replay past states (`time_machine.py`) to compare decisions against what actually happened.
- **Closed-loop experiments** — A/B-style comparisons between agent policy vs. baseline (`closed_loop_experiment.py`).

### Event engine (`services/event_engine.py`, `routers/events.py`)
Typed event registry, event subscriptions, batch ingestion, webhook fan-out (`webhook_events`), and event-derived knowledge-graph edges.

### POS integrations (`app/adapters/`, `routers/pos_webhooks.py`)
- **Foodics** and **Salla** webhooks with HMAC-SHA256 signature verification and per-tenant `pos_connections`.
- `item_resolver.py` maps POS items onto the catalog; adapter registry + periodic sync tasks in `app/tasks/pos_sync_tasks.py`.

### Compliance & privacy (`routers/compliance.py`)
GDPR / PDPL data export (`GET /api/v1/compliance/export/{id}`) and erasure (`DELETE /api/v1/compliance/delete/{id}`), processed asynchronously with pending-deletion records.

### Partners, billing & subscriptions (`routers/partners.py`, `routers/subscriptions.py`, `routers/organizations.py`)
- Partner program (accountants / Monshaat advisors) with application, dashboard, and public directory.
- Subscriptions, plans, usage metering, checkout; multi-store **organizations** with chain dashboards, teams, roles, and invite flows.

### Forecasting & operations (`routers/forecast.py`, `services/prophet_service.py`, `anomaly_detector.py`)
Prophet-backed demand forecast with TTL cache, plus rule-based anomaly detection; health/readiness/live probes (`routers/health.py`), startup checks, backup service, and an ops/pilot console.

> **Feature gating:** several routers are only registered when their flag is on — `BILLING_ENABLED` (subscriptions, organizations, adapters, actions), `CHAT_ENABLED` (chat), `AGENT_ENABLED` (agent), `VERTICAL_PHARMACY` (pharmacy). With `BILLING_ENABLED=false` the API boots in "KSA Implementation mode".

---

## API surface

NazmOS exposes **174 endpoints**. Interactive docs are live at `/docs` on any running backend; the full OpenAPI contract is committed at [`backend/docs/openapi.json`](backend/docs/openapi.json). Every response carries `X-NazmOS-API-Version: 2.1.0-ksa`.

> Versioned changelog: [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

| Group | Purpose | Key endpoints |
|---|---|---|
| Auth | Registration, login, sessions, refresh | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me` |
| OAuth | Social/OAuth login flows | `GET/POST /api/v1/oauth/…` |
| Businesses | Tenant bootstrap & context | `POST /api/v1/businesses/bootstrap`, `GET /api/v1/businesses/current` |
| Upload / ETL | Import messy CSV/XLS/XLSX | `POST /api/v1/upload/`, `POST /api/v1/upload/{id}/map`, `GET /api/v1/upload/{id}/status` |
| Guest Audit | Audit without sign-up | `POST /api/v1/guest-audit` |
| Money Audit | The core recovery loop | `POST /api/v1/money-audit/generate`, `POST .../actions/{id}/approve`, `POST .../actions/{id}/complete`, `GET .../whatsapp-summary` |
| Recovery Match | Nearby-store stock matching | `GET /api/v1/recovery-match/preview`, `GET /api/v1/recovery-match/matches`, `POST .../matches/{id}/reveal-contact` |
| Ops / Pilot console | Founder/operator consoles | `GET /api/v1/ops/pilot-console`, `GET /api/v1/pilot/…` (platform operator only) |
| Agent OS | Rule-based business agents | `POST /api/v1/agent/scan`, `GET /api/v1/agent/feed`, `POST /api/v1/agent/reason` |
| Intelligence | Reasoning, planning, memory, graphs | `POST /api/v1/intelligence/analyze`, `POST /api/v1/intelligence/plan`, `POST /api/v1/intelligence/simulate` |
| Decisions | Explainable decision logs | `GET /api/v1/decisions/…`, `POST .../feedback` |
| Forecast | Demand forecasting | `GET /api/v1/forecast/…` |
| Pharmacy | Expiry / FEFO / SFDA vertical | `GET,POST /api/v1/pharmacy/lots`, `GET /api/v1/pharmacy/recalls` |
| POS webhooks | Foodics + Salla integrations | `POST /api/v1/pos/foodics/webhook`, `POST /api/v1/pos/salla/webhook` |
| Adapters | POS adapter management | `GET,POST /api/v1/adapters/…` |
| WhatsApp | Approval bridge (mock $0 / live) | `GET,POST /api/v1/whatsapp/webhook`, `POST /api/v1/whatsapp/test-approve/{id}` |
| Partners | Accountants / Monshaat advisors | `POST /api/v1/partners/apply`, `GET /api/v1/partners/dashboard`, `GET /api/v1/partners/public` |
| Suppliers | Supplier network moat | `GET /api/v1/suppliers`, `GET /api/v1/suppliers/purchase-orders` |
| Purchase orders | POs with per-line receipt tracking | `GET,POST /api/v1/suppliers/purchase-orders/…` |
| Compliance | GDPR / PDPL erasure & export | `GET /api/v1/compliance/export/{id}`, `DELETE /api/v1/compliance/delete/{id}` |
| Dashboard | KPIs, trends, alerts | `GET /api/v1/dashboard/summary`, `GET .../alerts`, `GET .../top-products` |
| Inventory | Stock, details, restock | `GET /api/v1/inventory`, `GET /api/v1/inventory/{id}/detail`, `POST /api/v1/inventory/restock` |
| Subscriptions / Billing | Plans, usage, checkout | `GET /api/v1/subscriptions/plans`, `POST /api/v1/subscriptions/checkout`, `GET /api/v1/subscriptions/usage` |
| Organizations | Multi-store chains & teams | `GET /api/v1/organizations/`, `GET .../chain/dashboard`, `POST .../team/invite` |
| Events | Event engine & subscriptions | `GET,POST /api/v1/events`, `POST /api/v1/events/batch` |
| Orchestrator | Cross-feature orchestration | `GET,POST /api/v1/orchestrator/…` |
| Admin | Backups & audits | `GET /api/v1/admin-backup/…`, `GET /api/v1/audits/…` |
| Health & Ops | Health, readiness, metrics | `GET /api/v1/health`, `GET /api/v1/ready`, `GET /api/v1/live`, `GET /metrics` |

> Auth is required for all merchant endpoints; the ops console additionally requires the **platform-operator** identity (see [Security model](#security-model)). `/metrics` is optionally token-protected via `METRICS_TOKEN`.

---

## Security model

- **JWT authentication** — access + refresh tokens (PyJWT, HS256), role-based access, per-environment token lifetimes.
- **PostgreSQL Row-Level Security (RLS)** — tenant-isolation policies across 29+ business-scoped tables. The connection issues `SET ROLE nazmos_app` after setting `app.current_tenant_id`, so policies are enforced even though the migration user owns the tables. The restricted role is created idempotently by Alembic revision `33dd43e565ed`.
- **Capability-based authorization** — a single server-side capability model (see [`docs/ACCESS_MODEL.md`](docs/ACCESS_MODEL.md)) gates every route; the ops console is strictly **platform-operator** only (DB flag or `FOUNDER_EMAILS` allowlist).
- **Cross-tenant protections** — RLS middleware plus dedicated IDOR cross-tenant tests (`tests/security/test_idor_cross_tenant.py`); idempotency keys are tenant-scoped.
- **Idempotency keys** for safe retries of POST/PATCH/PUT (`Idempotency-Key` header, `idempotency_keys` table).
- **Credential vault** — AES-encrypted POS/integration secrets behind `CREDENTIAL_MASTER_KEY` (no dev fallback in production).
- **PII-redacted structured logs** — passwords, tokens, emails, phones, and other sensitive fields are scrubbed before logging.
- **Production fail-closed checks** — startup validation raises for missing Sentry/Llama keys, default `SECRET_KEY`, mock-LLM in prod, SQLite in prod, short vault keys, or misconfigured CORS.
- **Dependency CVE gate** — CI blocks on high/critical `pip-audit` findings.

---

## Data model

Backend models live in one module — `backend/app/database/models.py` — declaring **76 tables** (+ enums) via SQLAlchemy 2.0 `DeclarativeBase`.

| Area | Tables |
|---|---|
| Auth / tenant | `users`, `businesses`, `organizations`, `team_members`, `team_invitations`, `permission_definitions`, `enabled_modules` |
| Catalog / ops | `categories`, `items`, `inventory`, `transactions`, `daily_summaries`, `uploaded_files`, `pricing_rules`, `pricing_recommendations`, `purchase_orders`, `suppliers`, `supplier_prices` |
| Audit / finance | `audit_log`, `audit_runs`, `findings`, `money_audits`, `money_audit_actions`, `impact_ledger`, `executed_actions`, `constraint_blocks` |
| Recovery | `recovery_match_settings`, `stock_recovery_listings`, `stock_recovery_matches`, `stock_recovery_events` |
| Agent / decisions | `agent_actions`, `agent_runs`, `autonomy_policies`, `intelligence_decisions`, `outcome_feedback`, `model_performance`, `plans`, `simulations`, `execution_jobs` |
| Memory / learning | `business_memory`, `memory_updates`, `business_context`, `business_goals`, `learned_outcomes`, `goal_progress_history`, `graph_entities`, `graph_relationships`, `event_derivations` |
| Events | `events`, `event_types`, `event_subscriptions`, `webhook_events`, `pos_sync_logs` |
| Chat / AI | `chat_sessions`, `chat_messages`, `forecast_cache` |
| Billing / partners | `subscriptions`, `subscription_usage`, `billing_events`, `partners`, `partner_referrals` |
| Plumbing / security | `feature_flags`, `feature_flag_overrides`, `idempotency_keys`, `deletion_requests`, `notifications`, `notification_preferences`, `reports`, `analytics_cache`, `pilot_baselines` |
| Vertical | `pharmacy_lots`, `sfda_recalls`, `recipes`, `parts_compatibility` |

Schema migrations are managed with Alembic; `alembic/versions/` contains **42 revisions** covering 14+ phases (initial schema → tenant RLS → intelligence/recovery tables → learning engine → partner program → PO receipts → pilot baselines → RLS on core business tables). See [`docs/phase_a_audit/NAZMOS_DATABASE_ARCHITECTURE.md`](docs/phase_a_audit/NAZMOS_DATABASE_ARCHITECTURE.md) for a deeper look.

---

## Frontend

A Next.js 16 (App Router) single-page application that talks to the backend through a BFF route rewrite (`/api/v1/*` → backend) with secure token cookies.

### Routes / pages

| Area | Routes |
|---|---|
| Landing & guest | `/`, `/demo`, `/product-demo`, `/privacy`, `/terms`, `/ui-kit`, `/mobile`, `/partners` |
| Auth | `/login`, `/register`, `/onboarding` |
| Dashboard | `/dashboard`, `/feed`, `/chat`, `/chain`, `/findings/[id]`, `/forecast` |
| Recovery | `/upload`, `/money-audit`, `/recovery-match`, `/weekly-report`, `/inventory`, `/inventory/expiry`, `/suppliers` |
| Control | `/ops`, `/orchestrator`, `/integrations`, `/team`, `/settings/autonomy` |

Redirects: `/app`→`/feed`, `/signin`→`/login`, `/signup`→`/register`.

### Client architecture

- **State** — Zustand stores (`appStore`, `authStore`, `demoStore`) with route-guard access control (`RouteGuard`).
- **Data** — typed API client in `lib/api.ts`; Axios + React Query-style hooks (`useDashboard`, `useInventory`, `useIntelligence…`).
- **Forms** — React Hook Form + Zod validation.
- **Design system** — `design-tokens/tokens.json` (OKLCH) drives `tailwind.config.ts` via a build script; components in `src/components/ui/`.
- **i18n** — `lib/translations/{ar,en}.ts`; Arabic-first with full RTL.
- **Charts** — Recharts (sales trends, KPIs); animated counters via `@number-flow/react`.
- **Accessibility** — axe-core scans in CI + design-system ESLint rules.

---

## Quick start

### Option A — Zero-cost (SQLite, no Docker dependencies) ⭐

```bash
docker compose -f docker-compose.sqlite.yml up --build
```

- Backend: http://localhost:8000 · Docs: http://localhost:8000/docs · Frontend: http://localhost:3000

### Option B — Full local stack (Postgres 17 + Redis + Celery + frontend)

```bash
docker compose -f docker-compose.local.yml up --build
```

- Frontend: http://localhost:3000 · Backend: http://localhost:8000 · Docs: http://localhost:8000/docs
- The compose file runs migrations, then the backend, Celery worker + beat, Redis with persistence, and a seeded demo-friendly Postgres.
- Refer to [`docker-compose.local.yml`](docker-compose.local.yml) for the default local credentials; real secrets are supplied at deploy time, never committed.

### Option C — Production-like local / staging stack

```bash
docker compose up --build           # Postgres, Redis, API, Celery worker + beat, nginx, Prometheus, Grafana
docker compose -f docker-compose.prod.yml up --build   # production
```

- Grafana: http://localhost:3000 (admin/admin) · Prometheus: http://localhost:9090 · nginx on 80/443.

### Option D — Manual backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --reload
```

### Manual frontend

```bash
cd frontend
npm install
npm run dev
```

### Running / verifying migrations

```bash
cd backend
python -m alembic heads            # print the current head revision(s)
python -m alembic upgrade head     # apply all pending migrations
python -m alembic current          # what the DB is actually at
python -m alembic downgrade -1     # roll back one step (dev only)
```

### Ops console access

The pilot console (`/ops`) requires the platform-operator identity — granted via the founder/operator allowlist in the backend configuration, or by setting `is_platform_operator=true` on the user row in the database (see [Security model](#security-model)).

### Demo data

When demo seeding is enabled (the SQLite compose), the backend seeds demo retail data. Sample CSV exports for upload flows ship in [`sample_data/`](sample_data/).

---

## LLM providers

NazmOS talks to LLMs **directly** (no gateway). Supported providers:

| Provider | Notes |
|---|---|
| Groq | Fast, cheap inference |
| Google Gemini | `gemini-2.5-flash-lite` default |
| Mock | Deterministic rule-based responses at $0 — no keys needed |

A provider order controls failover (`groq → google → mock` by default, each with its own key). An optional call ledger records every LLM call to a JSONL file for cost/traceability audits. Prompts are sanitized (`prompt_sanitizer.py`) and responses validated (`ai_response_validator.py`) before use. Rate limiting is per-provider (`llm_rate_limiter.py`).

---

## WhatsApp approvals

The approval bridge turns any money-audit action into a WhatsApp message the owner can approve or reject from their phone.

- **Mock mode (default, $0)** — generates deep links to a phone-prefilled WhatsApp message and exposes a `test-approve` endpoint for local demos.
- **Live mode** — talks to the WhatsApp Business Cloud API with a token + phone ID; webhook verifies tokens and app secrets.

The bridge is implemented in `services/whatsapp_bridge.py` with `GET/POST /api/v1/whatsapp/webhook` and `POST /api/v1/whatsapp/test-approve/{id}`.

---

## Storage backends

Uploads and artifacts are stored via a pluggable layer (`services/storage.py`):

| Backend | When to use |
|---|---|
| `local` (default) | Dev / single-node / SQLite mode |
| `s3` | AWS S3 in production |
| `minio` | Self-hosted S3-compatible storage |

Bulked together with billing/files lives the `uploads/` directory (mounted as a volume in compose). Backups are produced by `deployment/nazmos-backup.{service,timer}` + `scripts/backup_postgres.py`.

---

## Background jobs (Celery)

When `USE_CELERY=true`, `app/celery_app.py` defines a Celery app with Redis broker/backend and **nine beat tasks**:

| Task | Schedule | Purpose |
|---|---|---|
| `refresh_all_forecasts` | daily 03:00 | Regenerate Prophet forecasts |
| `rebuild_summaries_yesterday` | daily 01:00 | Daily analytics rollups |
| `cleanup_stale_uploads` | daily 02:00 | Expire stale uploads |
| `process_pending_deletions` | daily 04:00 | GDPR/PDPL erasure work |
| `process_unprocessed_events` | every 60s | Event engine pump |
| `refresh_model_performance` | daily 05:00 | Learning-engine scoring |
| `daily_full_audit` | daily 06:00 | Periodic full money audit |
| `goal_progress_snapshot` | daily 07:00 | Goal progress history |
| `learning_reconciliation` | hourly | Reconcile learned outcomes |

**Queues:** `celery` (default), `forecasting`, `ingestion`, `analytics`, `dead_letter`. Task failures are routed to the dead-letter queue and logged.

When `USE_CELERY=false`, the same work runs in-process via FastAPI `BackgroundTasks`, so zero-cost mode needs no worker.

---

## Testing & CI

### Backend (`backend/`)

`105` test modules (≈917 tests). Categories include:

- **Phase / learning suites** — `test_phase0_event_engine` … `test_phase13_closed_loop`, `test_decision_engine`, `test_learning_engine`, `test_learning_advanced`, `test_context_temporal`, `test_knowledge_graph`.
- **Contract & RLS** — `test_retail_recovery_contract`, `test_rls_enforcement`, `test_rls_code_prep`, `test_rls_coverage_complete`, `test_rls_predicate_indexes`, `tests/security/test_idor_cross_tenant`, `test_legacy_isolation` (plus cross-tenant coverage inside `test_phase{1,2,6,8,11}_*`).
- **Security & hardening** — `test_security`, `test_pii_redaction`, `test_production_config_contract`, `test_production_hardening`, `test_credential_vault_production`, `test_compliance_gdpr`.
- **API groups** — `test_auth`, `test_upload`, `test_etl_pipeline`, `test_dashboard`, `test_inventory`, `test_money_audit` (in contract), `test_recovery_match_*`, `test_suppliers`, `test_subscriptions`, `test_partner_program`, `test_forecast`, `test_chat`, `test_infra_service`.
- **Reality / integration** — `test_openapi_contract`, `test_openapi`, `test_zero_cost_sqlite_mode`, `test_celery_deployment`, `test_chaos_engineering`, `test_v8_ai_adversarial`, `test_reality_v2_protocol`.

```bash
cd backend
pytest -q                              # full suite (needs Postgres at DATABASE_URL)
PYTHONPATH=. python -m compileall -q app tests
PYTHONPATH=. python -m alembic heads
```

### Frontend (`frontend/`)

```bash
cd frontend
npm run lint                           # ESLint 9 flat config + design-system rules
npm run build                          # production build (`output: standalone`)
npm test -- --ci --runInBand           # Jest (ts-jest + jsdom, Testing Library)
npm audit --audit-level=moderate --omit=dev
npx playwright test                    # E2E specs under frontend/e2e/ (chromium, authed state)
node scripts/check_frontend_routes.mjs # route/link integrity check
node scripts/check_a11y.mjs            # axe-core accessibility scan
```

### Workspace helpers (`Makefile`)

```bash
make verify               # scripts/verify_workspace.py
make backend-test         # pytest + compileall + alembic heads
make frontend-test        # lint + build + audit
make contract             # retail recovery contract test
make runtime-smoke        # runtime_smoke.py
make runtime-e2e          # runtime_e2e_upload_money_audit.py
make local-up / local-down
make runtime-up / runtime-down / runtime-logs / runtime-readiness
```

### CI (`.github/workflows/ci.yml`)

Runs on push to `main`/`master` and PRs:

- **backend job** (Python 3.13, Postgres 17 + Redis services)
  1. `pip install -r backend/requirements.txt`
  2. `compileall` (app/tests + scripts) and `alembic heads`
  3. `pip-audit` → **blocks CI on high/critical CVEs**
  4. `alembic upgrade head` + `pytest -q` against PostgreSQL
  5. Runtime E2E smoke: boot `uvicorn`, run `runtime_e2e_upload_money_audit.py` + `runtime_e2e_demo_ksa_retail.py`, then kill server
- **frontend job** (Node 20)
  1. `npm ci`
  2. `npm run lint` + `npm run build` + `npm audit`
  3. Jest unit tests
  4. route/link integrity check (`check_frontend_routes.mjs`)
  5. axe accessibility scan (`check_a11y.mjs`)

---

## Deployment & operations

- **Zero-cost**: `docker-compose.sqlite.yml` — SQLite + in-process tasks + mock LLM + browser-side ETL.
- **Full local**: `docker-compose.local.yml` — Postgres 17, Redis, migrate-first, API, Celery worker + beat, frontend.
- **Production-like local / staging**: `docker-compose.yml` — Postgres, Redis, API, Celery worker + beat, nginx, Prometheus, Grafana.
- **Production**: `docker-compose.prod.yml`.
- **Cloud provisioning**: `infrastructure/terraform/`.
- **Backups**: `deployment/nazmos-backup.{service,timer}` + `scripts/backup_postgres.py`.
- **Monitoring**: Prometheus scrape config in `backend/monitoring/prometheus.yml`, Grafana dashboards + provisioning in `backend/monitoring/grafana/`; `/metrics` endpoint is token-protected via `METRICS_TOKEN`.
- **Runbooks**: [`docs/runbooks.md`](docs/runbooks.md).
- **Pilot SOP**: [`docs/PILOT_SOP.md`](docs/PILOT_SOP.md) — controlled-pilot operating procedure.
- **Systemd** health probes: `backend/scripts/runtime_{worker,beat}_health.py`.

---

## Project structure

```
NazmOS/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, lifespan checks, router registration
│   │   ├── config.py             # pydantic-settings (all env vars)
│   │   ├── celery_app.py         # Celery app, queues, beat schedule
│   │   ├── routers/              # 32 router modules (30 registered)
│   │   │   ├── auth.py businesses.py upload.py money_audit.py recovery_match.py
│   │   │   ├── intelligence.py agent.py suppliers.py pharmacy.py partners.py
│   │   │   ├── ops.py pilot.py orchestrator.py chat.py oauth.py compliance.py
│   │   │   └── … (health, dashboard, inventory, decisions, events, forecast, …)
│   │   ├── services/             # ~115 business-logic modules
│   │   │   ├── money_audit_service.py etl_pipeline.py data_normalizer.py
│   │   │   ├── decision_engine.py learning_engine.py knowledge_graph.py
│   │   │   ├── event_engine.py recovery_intelligence.py llm_orchestrator.py
│   │   │   ├── whatsapp_bridge.py credential_vault.py subscription_service.py
│   │   │   └── … (agents, planning, simulation, pilot, backup, analytics, …)
│   │   ├── intelligence/agents/  # margin, pricing, inventory, procurement,
│   │   │                         # recovery, finance, compliance, supplier agents
│   │   ├── middleware/           # auth, RLS tenant, RBAC, idempotency, rate-limit,
│   │   │                         # logging (PII-redacted), Prometheus, API-version
│   │   ├── database/             # models.py (76 tables), connection, seed
│   │   ├── adapters/             # foodics, salla, item_resolver, registry
│   │   ├── tasks/                # celery task modules (forecast, ingest, analytics,…)
│   │   ├── schemas/              # Pydantic DTOs
│   │   └── utils/                # security, tracing, problem-details, startup checks
│   ├── alembic/versions/         # 42 migration revisions (RLS, learning, PO, pilot…)
│   ├── docs/openapi.json         # committed OpenAPI golden (174 endpoints)
│   ├── monitoring/               # Prometheus + Grafana provisioning
│   ├── nginx/                    # nginx.conf for the compose stack
│   └── tests/                    # 105 test modules
├── frontend/
│   ├── src/
│   │   ├── app/                  # App Router: (dashboard), (auth), landing, privacy…
│   │   ├── components/           # ui/, dashboard/, money-audit/, upload/, layout/…
│   │   ├── hooks/ lib/ stores/ types/
│   ├── e2e/                      # Playwright specs (auth, dashboard, upload, owner-journey…)
│   ├── design-tokens/            # tokens.json → tailwind.config.ts
│   └── e2e-config files          # jest.config.mjs, playwright.config.ts, eslint.config.mjs
├── scripts/                      # E2E, smoke, backup/restore, demo-data generators
├── sample_data/                  # Sample CSV exports for demos
├── infrastructure/terraform/     # Cloud provisioning
├── deployment/                   # systemd backup units
├── docs/                         # All docs — runbooks, pilot SOP, architecture audits,
│                                 # phase reports, reality-test evidence (monorepo root
│                                 # keeps only this README)
└── README.md
```

---

## Documentation index

| Doc | What it covers |
|---|---|
| [`docs/README_KSA.md`](docs/README_KSA.md) | KSA merchant pitch (Arabic market) |
| [`docs/ACCESS_MODEL.md`](docs/ACCESS_MODEL.md) | Capability & authorization model |
| [`docs/HANDOVER_KSA.md`](docs/HANDOVER_KSA.md) | KSA handover notes |
| [`docs/PILOT_SOP.md`](docs/PILOT_SOP.md) | Controlled-pilot operating procedure |
| [`docs/runbooks.md`](docs/runbooks.md) | Production runbooks & ops |
| [`backend/docs/openapi.json`](backend/docs/openapi.json) | Full OpenAPI contract |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | API changelog |
| [`docs/FRONTEND_PAGE_MAP.md`](docs/FRONTEND_PAGE_MAP.md) | Frontend page ↔ endpoint map |
| [`docs/phase_a_audit/`](docs/phase_a_audit/) | System architecture, DB architecture, data flow, integrations, tenant isolation, customer journey (code-level) |
| [`docs/RECOMMENDATION_ENGINE.md`](docs/RECOMMENDATION_ENGINE.md) | Recommendation engine internals |
| [`docs/REPLAYABILITY.md`](docs/REPLAYABILITY.md) | Time-machine / repro design |
| [`docs/NAZMOS_INTELLIGENCE_ARCHITECTURE_PLAN.md`](docs/NAZMOS_INTELLIGENCE_ARCHITECTURE_PLAN.md) | Intelligence architecture plan |
| `docs/PHASE{0–13}_REPORT.md` | Per-phase implementation reports |
| `docs/NAZMOS_V{6–12}_REALITY_TEST_REPORT.md` | Reality-test evidence runs |
| [`docs/TESTING_REPORT.md`](docs/TESTING_REPORT.md) | End-to-end testing summary |

---

## Roadmap phases

The codebase tracks 14 named implementation phases (`PHASE0` → `PHASE13`), each with its own report at the repo root:

- **Phase 0** — Event engine · **Phase 1** — Decision safety & business-memory foundation · **Phase 2** — Knowledge graph · **Phase 3** — Context & temporal reasoning · **Phase 4** — Decision explainability · **Phase 5** — Agents, planning, simulation, execution · **Phase 6** — Learning engine · **Phase 7** — App refactor + intelligence API · **Phase 8** — Partner program + suppliers · **Phase 9** — Concurrency & systems hardening · **Phase 10** — Scaling · **Phase 11** — Agent orchestration · **Phase 12** — Adaptation & closed-loop experiments · **Phase 13** — Closed-loop validation & prioritization.

Cross-cutting: **Track 2** E2E evidence, **Track 3** UX research/verification, and a **Production hardening** pass (backup, monitoring, RLS enforcement, fail-closed startup).

---

## License

Proprietary. © Nazmak. All rights reserved. This repository is not open-source and may not be copied, redistributed, or used commercially without written permission.