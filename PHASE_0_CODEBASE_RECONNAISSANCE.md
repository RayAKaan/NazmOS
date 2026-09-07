# PHASE 0 — COMPLETE CODEBASE RECONNAISSANCE

**Scope.** Read-only investigation of the entire NazmOS codebase. Goal: understand at code level what was actually built (§1–§32), then recommend **exactly three** custom self-built subsystems to replace with proven open-source software (Batch 1, Appendix D). No code was modified, no dependencies installed, nothing refactored or deleted.

**Method.** 9 domain exploration agents + 2 follow-up agents, all findings cross-checked against source with `file:line` evidence. Where a claim could not be established from code it is marked exactly as:

> `UNKNOWN — NOT ESTABLISHED FROM CODE`

**Source of truth.** Code only. Docs/reports (including this repo's `backend/docs/item7…item11`, `docs/`) and git history are *secondary* evidence and are only cited where they corroborate code.

**Repo identity.** `NAZMOS_LATEST_MERGED`, git `main` @ `f8f7fb9cc` (`fix(ci): resolve chat import NameError and bandit B608 findings`), origin `git@github.com:RayAKaan/NazmOS.git`, working tree clean.

---

## §1 Report scope, rules & method

- Read-only. No production code, tests, or migrations changed.
- Every numbered finding carries a `path:line` citation. Cross-cutting evidence is consolidated in §29 (duplicate logic), §30 (constants), §31 (silent failures), Appendix A (dependencies).
- Frontier of uncertainty is closed explicitly with the `UNKNOWN — NOT ESTABLISHED FROM CODE` marker (Appendix E collects all registered unknowns).
- Batch-1 recommendation is grounded in the duplicate-matrix (§29) and custom-infra pool (Appendix B), not in trade-journal preferences.

## §2 Repository state & provenance

| Item | Evidence |
|---|---|
| Branch | `main` |
| HEAD | `f8f7fb9cc` (CI-fix commit) |
| Preceding commit | `e20054e` (Items 1–11 remediation; ~120 files) |
| Remote | `origin` = `github.com/RayAKaan/NazmOS.git` |
| Cleanliness | working tree clean, nothing unpushed |
| CI gate | `.github/workflows/ci.yml` (security-scan, backend, frontend, token-guard) — green at HEAD |

Root artifacts: `PHASE_0_TOKEN_AUDIT_REPORT.md`, `NAZMOS_LATEST_MERGED_MANIFEST.json`, `.gitleaks.toml`, `docker-compose*.yml`, `Makefile`-analogues via `scripts/`.

## §3 Top-level structure

```
.github/workflows/        ci.yml, deploy.yml, backup.yml
backend/
  app/                    FastAPI app (main, routers, services, middleware, intelligence, adapters, security, database)
  alembic/                migrations, single head ff08
  tests/                  1109 test fns (unit/regression/adversarial/load/phase*) + reality fixtures
  requirements.txt        pinned deps, cvss artifacts via check-deps
frontend/                 Next.js 16.3.0 app router + jest 30 + Playwright e2e
infrastructure/           Terraform: GCP (VPC, Cloud SQL PG, Redis, GCS, Secret Manager, Cloud Run, Cloud Armor/LB)
deployment/               systemd: nazmos-backup.service + .timer
e2e/                      root-level Playwright spec(s); /e2e/phase6-owner-journey.spec.ts is ORPHAN (not CI-referenced)
reality_fixture/ reality_test_output/   offline adversarial reality fixtures (partial; output dir gitignored)
results/                  versioned run artifacts v9…v12
sample_data/ uploads/ scripts/          seed CSVs, local persisted uploads, ops scripts
```

- `root/e2e/*` is disconnected from CI; the *maintained* e2e suite lives in `frontend/e2e/` (13 specs) — see §32.

## §4 Build, run, deployment entry points

- **Backend**: FastAPI 2.x + SQLAlchemy 2 asyncio + `asyncpg`; uvicorn entry `backend/app/main.py` (module-level `app` at `main.py:135-140`; lifespan `main.py:47-132` which bootstraps OpenTelemetry, Sentry, dev `create_all`, seed flags, startup checks).
- **Frontend**: Next.js 16.3.0; BFF proxying in `frontend/src/app/api/v1/[...path]/route.ts` + `frontend/src/lib/bff-proxy.ts`; jest config `frontend/jest.config.mjs`, Playwright `frontend/playwright*.config.ts`.
- **Local/CI**: `docker-compose*.yml` (postgres, redis, backend, frontend); CI backend job runs `alembic upgrade head` then pytest against `nazmos_dev` Postgres service (`POSTGRES_PASSWORD: nazmos_dev`); **local** test DB is `nazmos_v5_dev` (env override), asyncpg URL prefixed `postgresql+asyncpg://`.
- **Prod shape (code-only)**: GCP terraform (Cloud Run + Cloud SQL + Redis + GCS + Secret Manager); systemd backup timer `deployment/nazmos-backup.service` / `.timer`. `UNKNOWN — NOT ESTABLISHED FROM CODE`: actual running topology at the two SSH endpoints (staging/prod) is not observable from the repo.
- **Env swizzle points**: `.env.example`, `.env.runtime-test(.example)`, `backend/app/config.py`.

## §5 Backend runtime & application lifecycle

- Startup (`main.py:47-132`): OTel attempt (optional dep absent locally), Sentry init, DB ping, dev-only `create_all`, startup feature-flag seeding, `/health` readiness.
- Middleware order (request →): RateLimit → Prometheus → TenantContext → Idempotency → SecurityHeaders → Logging → Deprecation → APIVersion → CORS (`main.py:146-183`; `add_middleware` wrapping order).
- TenantContextMiddleware performs JWT decode itself and stamps `business_id` + sets RLS (`middleware/rls_tenant.py:86-92`).
- Routers registered in `main.py:189-270`; conditionally included: chat (feature-flagged), chest/rls-experiment, etc. 250 route decorators across `routers/` (~228 routes as service-discovered earlier; decorator count ≠ route count because of shared paths/dynamic segments).
- Idempotency is tenant-scoped (test: `tests/test_idempotency_tenant_scope.py`).

## §6 API surface & router map

Route families (all under `/api/v1`): auth, oauth, users, business, locations, items, inventory, branches, daily-summaries, analytics, dashboard, suppliers, purchase-orders, upload (`/upload`, `/upload/map`), ingest-json, etl, guest-audit, money-audit (+`/evidence`, `/time_machine`, `/recoveries`, `/generate`), recovery-match, forecasting (`/forecast`, `/forecasting`), intelligence (`/brain`, `/challenge`, `/execute`), decisions, actions (`/execute`, `/{id}/reverse`, `/decisions/{id}/apply`), agent (`/run`, `/actions/{id}/approve|reject`, `/autonomy`), ops, pharmacy, partners, compliance, events, plans/simulations, business-memory, whatsapp webhook, pos webhooks (foodics/salla), oauth, health (`/health`, `/health/redis`, `/health/celery`), security audit endpoints.

- Guest-audit route is **unauthenticated by design** (`routers/guest_audit.py`).
- POS webhooks are **unauthenticated, HMAC-signed** body-verified (`routers/pos_webhooks.py`).
- WhatsApp router ships a `test-approve/{action_id}` simulator "disabled in production" (`routers/whatsapp.py:125-139`) — gate is env-based; see §30.

## §7 Configuration & feature flags

Default flags (`config.py`, `get_settings`): `CHAT_ENABLED=false`, `VERTICAL_PHARMACY=true`, `BILLING_ENABLED=false`, `USE_CELERY=false`, `USE_REDIS=false`, `USE_CLIENT_ETL=false`, `AGENT_AUTO_MIN_CONFIDENCE=0.90` (`config.py:110`), `RISK_ESCALATE_MEDIUM_SAR=5000.0` (`config.py:108`), `WHATSAPP_VERIFY_TOKEN` ships a default secret value and warns only in ap mode.

Notable env-derived behaviors:
- SQLite mode silently disables Celery and RLS health paths (`zero-cost` DataFrame path; see §24).
- `USE_CELERY=false` + background income deferred to sync paths (`forecasting/sync_runner.py`).

## §8 Authentication

- JWT (access/refresh) via `routers/auth.py`; `lib/session.ts` mirrors the 15m/30d cookie lifetime on the frontend (`nazm_access` / `nazm_refresh`).
- OAuth flows exist (`routers/oauth.py`) with **in-memory state store** — `UNKNOWN — NOT ESTABLISHED FROM CODE` for multi-instance correctness (oauth state is per-process).
- Password storage: passlib/bcrypt; `users.two_factor_secret` is the single `EncryptedText` column → field-level encryption is **one column**, not a vault.
- Backend rejects unauth'd business data via auth dependency + tenant forwarding; tenant is read from the JWT, *not* from a header (prevents tenant-spoofing).

## §9 Authorization & RBAC

- Capability model via `services/capabilities_service.py` + `require_capability(...)`; approval-gated routes use `require_capability("can_approve_actions", "business_id")` and `assert_capability_for_business` (e.g. `routers/money_audit.py:237,260,283,408`; `routers/agent.py:86,117,195`).
- Roles resolved from `business.owner_id` + `team_members` rows; there is **no role column per user** — role is a per-business derived state. Capability set is central, unit-tested (`tests/test_security_acceptance.py`, `tests/security/test_approval_authorization.py`).
- `execution_guard.py` reverify is **fail-open** (`services/execution_guard.py`; see §31), though DB mutations sit behind capability + approval.
- `UNKNOWN — NOT ESTABLISHED FROM CODE`: exact coarse-grain permission matrix beyond `owner/manage/staff` split; enumerate from `capabilities_service` at implementation time.

## §10 Row-Level Security (RLS)

- App role `nazmos_app`; per-table RLS policies are declared in `models.py` `__table_args__["info"]` dicts and enforced by tenant middleware.
- RLS coverage: present on core tenant tables (inventory, transactions, items, money_audits, recovery_*, forecast_cache, decisions, actions, etc.).
- **RLS gaps (verified)**:
  - `chat_messages` (and `chat_sessions`) rows are not tenant-prefixed by policy.
  - `pos_sync_logs` rows not tenant-prefixed.
- Celery-side: `sync_rls_tenant_context` is applied per-task in forecast/ingestion/audit/pos tasks; **analytics** (`analytics_tasks.rebuild_summaries_yesterday`, daily 01:00) and **learning** (`process_unprocessed_events`, `learning_reconciliation`) run with a sync session and flag `without_rls` — cross-tenant supervisors (see Item-11 report). Multi-tenancy of dashboard aggregates therefore UNKNOWN for those paths.

## §11 Data model & canonical grain

- Single `backend/app/database/models.py` documents **79 model entries** (users, businesses, locations, items, inventory, transactions, daily summaries, suppliers, purchase orders, money audits/actions, recovery items/matches/events, forecasts, decision logs, agent runs/actions, autonomy policy, executed actions, outcome feedback, impact ledger, learned outcomes, model performance, knowledge graph, business memory, events/event types/subscriptions/derivations, plans/simulations/execution jobs, intelligence decisions, security events, AI reasoning requests, constraint blocks, compliance/deletion-requests, recalls/recipes/parts, pharmacy lots, partner program, pilot baselines, …).
- **Canonical grain** = business + location + item + time + source, preserved throughout (dedup row_hash includes `business_id,item_id,location_id,source_transaction_id,transaction_at,quantity,total_amount`).
- Identity of an item is **name-based**: `items` have `sku`/`barcode`/`cost_price`/`sell_price` but item resolution falls back to name matching; no casefold/NFKC normalization in identity paths (`data_normalizer.py` normalizes display strings but not identity keys).
- `inventory` unique `(business_id, item_id, location_id)` + partial unique index allowing NULL-location (legacy pattern); `transactions` has a 4-column partial unique index for upsert.
- Encrypted columns: exactly one (`users.two_factor_secret`, `EncryptedText`).

## §12 Migrations & schema lineage

- Alembic, single linear head `ff08_loc_grain_tenant_model`; versions file `backend/alembic/versions/ff08_*.py`.
- CI executes `alembic upgrade head` before pytest — schema drift is caught by golden regression (28,892-row SQL fixture in `tests/regression/test_golden_fixture_regression.py`) plus `TestETLIntegration`.
- Dev mode may `create_all` skip migrations (`main.py` lifespan guards) — acceptable locally, doc-only.

## §13 Ingestion pipeline (upload → ETL → DB)

Endpoints (all above /api/v1):
- `POST /upload` (multipart CSV/XLSX/XLS; JSON rejected), `POST /upload/map` confirm-mapping → ETL (Celery queued when enabled, else inline).
- `POST /ingest-json` client-side rows (PapaParse) — used by `frontend` upload UI.
- `POST /guest-audit` **unauth** single/two-file upload or JSON rows (guest audit).
- `POST /pos/foodics/webhook`, `POST /pos/salla/webhook` HMAC-signed JSON.
- WhatsApp webhook = approve/reject + D2C, **not** ingestion.

Pipeline stages: FileValidator (extensions) → pandas read → `SchemaDetector` (header→column matching) → `column_profiling` → `data_normalizer` (strip/case/NFKC/Arabic normalization) → `semantic_mapping` (confidence-based, uses `conf_min` gates) → row-hash dedup → `ON CONFLICT` upsert → DB; items/suppliers/locations auto-created by name.

Known SchemaDetector header mis-mappings (verified in Item-11 + code):
- `transaction_id` → mapped to `transaction_at`
- `business_id` → mapped to `source_transaction_id`
- `transaction_type` → mapped to `storage_type`
- `location_id` → mapped to `location_name`
- `transaction_date` unmapped by default

These produce **column-diameter edge cases** the golden/adversarial suites partially cover; they are a correctness hazard for real merchant files (see §30).

## §14 Ingestion quality: dedup, identity, unknown/hostile data

- Dedup: deterministic row-hash + partial unique index warns/dedups on `ON CONFLICT`.
- Identity: item name string is the join key after `slice/trim`; duplicate-name items within a business resolved by AU-first-wins policy (auction rule); `UNKNOWN — NOT ESTABLISHED FROM CODE` for exact resolution lane when two names collide across synonyms.
- Unknown values: numeric gaps COALESCE to 0 / neutral types; missing dates rejected; negative stock/price rejected by schema validators (`schemas/edge_cases.py:29-59`); oversized amounts bounded (`edge_cases.py:58,159`).
- Location collapse: if data has multiple distinct location names under a single location id, ETL **fails closed** (no silent merge).
- Guest/simulated data can enter with fake/synthetic values; audit path marks simulators explicitly.

## §15 Money audit

- **Canonical financial core**: `services/audit_core.py` — `coverage_aware_daily_velocity(qty_30d, coverage_days)` is the single accepted velocity function; `TARGET_MARGIN_PCT = 0.22` (`audit_core.py:27`); `audit_core.py:161` composes inventory value on **cost** basis.
- Consumers of the canonical core: `money_audit_service.py`, `guest_audit_service.py`, `evidence_package.py`, `routers/money_audit.py` (time==), `recoveries`. Router even re-imble `coverage_aware_daily_velocity` in `routers/money_audit.py:882`.
- Stock-value basis is **non-uniform**:
  - cost basis: `audit_core.py:161`, `money_audit_service.py:350`, `branch_memory.py:104`, `business_context.py:130,169`, `chat.py:43`.
  - **sell** basis: `analytics_service.py:192`, `:774-777`, `:1032` → dashboard total-inventory-value ≠ money-audit total.
- `money_audit_service.py:18` TARGET_MARGIN 0.22; `evidence_package.py:61` default `target_margin_pct: float = 0.30` and `:243` passes 0.30 → **margin target disagreement 0.22 vs 0.30** in evidence generated for the same audit.
- Money-at-risk alias: `money_at_risk_sar` ⇔ `capital_at_risk_sar` (`models.py:1404-1406`, `money_audit_service.py:559-561`); frontend `ops/page.tsx:85` falls back `capital_at_risk_sar ?? money_at_risk_sar`.

## §16 Analytics & dashboard semantics

- `analytics_service.py` is the bespoke analytics layer: qty_30d subqueries (`:238`), dead-stock threshold sales `<1` (`:256`), trend decline `*0.95` (`:313`), sell-basis stock value (`:774,1032`), Thu/Fri demand multiplier `1.35` (`:920`).
- Duplicate velocity: `/30` arithmetic in `analytics_service.py:172,743,937,1115`; `root_cause.py:36,95,219`; `inventory_orchestrator.py:46`; `product_memory.py:257,539`; `branch_memory.py:119` — **ignores coverage** (padding day-counts), diverging from audit_core when coverage ≠ 30.
- Agent-side SQL re-implements `/30.0` + `NULLIF(...0.01)` inside raw queries: `intelligence/agents/inventory_agent.py:118-124`, `procurement_agent.py:45-54`, `agent_tools.py:92-106`.
- Dashboard aggregate revenues, average-basket, profit-toLocaleString and chart heights are derived **client-side** in frontend (see §29 for the derivation map); server analytics feeds raw numbers only.

## §17 Reconciliation & recovery

- Single source of classification: `recovery_intelligence.classify_inventory` (DEAD / SLOW / FAST / SEASONAL / OVERSTOCK / STOCKOUT) with threshold set {45d no-sale, 30d slow, ratio 0.1, overstock 1.5, stockout 0.6, 45d dead, 500 SAR threshold} (`recovery_intelligence.py:16` `TARGET_MARGIN=0.22`; `:127` legacy `/30` note).
- Recovery match: `recovery_match_service.py` (matcher + unit tests `tests/test_recovery_match_matcher.py`, contract `tests/test_retail_recovery_contract.py`).
- **Verified risk**: `recovery_match_service.complete_match` writes rows without re-checking party/business on the UPDATE; authorization audit exists (`tests/security/`).
- Capital-at-risk escalation: severity "high" when `expected_recovery_sar >= 5000` (`audit_engine.py:69,133`), matching `RISK_ESCALATE_MEDIUM_SAR` config (0.22 margin audit_vs_top-level agreement pending — see §29).

## §18 Forecasting

Three parallel implementations:
1. **Canonical** `services/forecasting/` package (`provider.py` interface; `prophet_provider.py` = Prophet engine; `data_builder.py`; `quality.py` gates; `retrieval.py`; `cache.py` writes `forecast_cache` with `provenance`+`provider` cols; `baseline_provider.py:152` hand-rolled weekday factors {0:0.88…6:0.95}; `sync_runner.py` no-celery path; `evaluation.py` MAPE).
2. **Legacy** `services/prophet_service.py` — duplicate Prophet orchestration; `:251` returns hardcoded `1.35` multiplier.
3. **Analytics bespoke fallback** `analytics_service.py:920` `1.35 if weekday in (Thu,Fri)` — a third demand-forecast rule with the same magic constant.

Consumers: forecast router endpoints, inventory reports, `nazm_planner.py` (`:238` 999-sentinel days-out), procurement/inventory agents, analytics lead/demand numbers. `forecast_tasks.refresh_all_forecasts` daily 03:00 with per-item RLS (safe path).

## §19 AI entry points & isolation

Three LLM entry points:
1. **Chat** `routers/chat.py` (import-fixed at `chat.py:8`), `ContextBuilder` → `prompt_engine` → `LLMOrchestrator` → `OutputGate`; gated by `CHAT_ENABLED`, plus global kill-switch and per-business `llm_requests_today` counters + `LLMRateLimit` (tests `test_llm_rate_limiter.py`).
2. **opencode-brain capsule path**: `/money-audit/generate`, `/intelligence/brain` → `services/opencode_brain.py` → `PrivacyFirewall.build_reasoning_capsule` → `Capsule.for_prompt` → OpenCode subprocess/runner transport → `OutputGate.validate_ai_output`.
3. **AI challenge** `/intelligence/challenge` (`services/ai_challenge.py`) adversarial self-tests.

Isolation properties (verified):
- Capsule = signed, banded, opaque (no SKUs/SAR/ids) — `security/capsule.py`, unit-tests `tests/security/test_capsule.py`, `test_privacy_firewall.py`.
- Output gate normalizes decision/confidence/evidence-ids/risk-flags/number formats (`security/output_gate.py`; tests `test_output_gate.py`).
- **AI is advisory**: no path lets the LLM write directly to DB. AI output can populate `agent_actions` rows that a deterministic executor later runs **after** approval (gate at `routers/agent.py` approve + `agent_action_executor.py`).
- `test_chat_no_fabricated_kpis.py` specifically protects "no invented KPIs".

## §20 Capsule, privacy firewall & output gate

Detailed in §19.2. Additional facts:
- `PrivacyFirewall` strips sensitive fields; `classification.py` marks `sell_price_sar` SENSITIVE (`security/classification.py:49`).
- Consent/redaction: `test_pii_redaction.py`, DLP gating (`test_dlp.py`); equality/safety harness `test_ai_isolation.py`.

## §21 Decision engine & classification

- `services/decision_engine.py` — pure-python rule engine; 999-sentinel days-left (`:70,71,118`), confidences 0.95/0.90 (`:137,153`), price-drop `*0.95` (`:353`), confidence floor 0.9 (`:529`).
- `nazm_planner.py` scoring: dial ≥95 threshold, priority by confidence buckets 0.9/0.75/0.6 (`:88,112`), `confidence=0.95` on plan rows (`:567`), 999-sentinel (`:238`), 0.92/0.85 conf (`:245`).
- Deterministic **agents** (`runtime.py:47,126`): `model_provider="deterministic"` — rules only, no LLM in the loop; agents self-score confidence (0.7–0.9 across inventory/procurement/finance/pricing/compliance/margin/recovery/supplier agents).
- `business_context.py` confidence 0.95/0.90 thresholds (`:401,428`) and `>5000 SAR` emphasis (`:450`).
- Classification consistency risk: agent thresholds (margin `<0.15` in `margin_agent.py:41`), Planning dial ≥95, audit margin 0.22 vs evidence 0.30 → **five independent margin/velocity/priority dials** (§29-30).

## §22 Approval paths

- Web: agent approve/reject (`routers/agent.py:86,117`), money-audit action approve (`routers/money_audit.py:228,283`), actions apply/reverse (`routers/actions.py:81,153`), intelligence execute (`routers/intelligence.py:615-622`), Ops. All gated by `can_approve_actions`.
- **WhatsApp**: button-id approve for price-shield/transfer/generic (`routers/whatsapp.py:79-96`) → `approve_agent_action`.
- Autonomy: `autonomy` slider 0/50/100 (`routers/agent.py:177`, `autonomy_service.py`), auto-exec floor `AGENT_AUTO_MIN_CONFIDENCE=0.90` (`autonomy_service.py:118`).
- State machine: pending → approved → executed → outcome; reversal allowed for price/stock actions (`actions.py:81`).

## §23 Execution engines & orchestration

Four+ parallel execution substrates:
1. `ActionExecutor` (`services/action_executor.py`) — price/restock/transfer/stock adj, record-mutation + outcome ingestion (`:374-395,449 price change`).
2. `AgentActionExecutor` — `approve_agent_action` / `reject_agent_action` (`services/agent_action_executor.py:33-68`): run-rule + row-mutation (updates `sell_price`).
3. `ExecutionGuard` — guard/reverify (fail-open), `services/execution_guard.py:91` maps `sell_price_sar` aliases.
4. `autonomy_service.py` + planners (`nazm_planner.py`, `ab_decision_framework.py`) — batch plan generation/apply paths.

Entry duplication: `POST /actions/execute` (`actions.py:26`), `/money-audit/{id}/execute` (`money_audit.py:389`), `/intelligence/execute` (`intelligence.py:616`), `agent/autonomy/evaluate` — each re-implements action-lifecycle handling; `action_registry.py` duplicates the price-flag predicate (`action_registry.py:36`) shared with `execution_guard.py`.

Reachability: many of these routes are account-authenticated with capability checks; **whichever engine runs is DB-mutating** (executed_actions, agent_actions, inventory, purchase_orders, item prices).

Outcome flow covers `actions`, `agent_actions`, `outcome_feedback`, `impact_ledger`, `learned_outcomes`.

## §24 Background jobs & queues

- `tasks/celery_app.py` — Celery **gated** by `USE_CELERY` (default off); stub mode queues nothing; SQLite mode auto-disables.
- Queues: celery, forecasting, ingestion, analytics, dead_letter.
- Registered schedules (code-verified in `tasks/`):
  - `rebuild_summaries_yesterday` — daily 01:00 (analytics; sync session; **no RLS**)
  - `refresh_all_forecasts` — daily 03:00 (per-item RLS ✓)
  - audit, learning (see §10 gap list), ingestion, compliance, business-memory, pos-sync, event tasks.
- `forecasting/sync_runner.py` provides the no-celery synchronous path so the product works with `USE_CELERY=false`.

## §25 Storage & backups

- Uploads: local filesystem (`uploads/` at repo root + volumes) — **no S3/GCS object path in code**.
- Backups: `services/backup_service.py` PG dump + restore-drill; systemd timer daily (deployment/).
- Secrets: env vars + (2FA-only) EncryptedText; no external KMS integration in app code.

## §26 Integrations

- **Implemented**: Foodics & Salla webhooks (HMAC, verified payload signing), WhatsApp interactive buttons (approve), OAuth (google) with in-memory state store, `adapters/registry.py` external-product mapping (multi-provider SKU/cost/price normalization).
- **Partial/stub**: Twilio/SendGrid (email/sms), Stripe subscription hooks, loyalty — `UNKNOWN — NOT ESTABLISHED FROM CODE` which adapters are live vs scaffold (registry present but per-provider cut-through verified only for Foodics/Salla).
- Pharmacy extensibility (`VERTICAL_PHARMACY`) exercises lot/expiry (`models.py` pharmacy_lots, `pharmacy.py:67`).

## §27 Observability & security eventing

- structlog (serialized logs, PII redact util), OpenTelemetry attempt (optional dep — locally absent; graceful skip in lifespan), Sentry (`SENTRY_DSN`), Prometheus `/metrics` + request middleware, `/health` + `/health/redis` + `/health/celery`.
- Security events written to `security_events` and `ai_reasoning_requests` (audit trail), covering webhook hmac-fail, tenant-mismatch, chat-gate triggers, approval trails (tests: `test_webhook_audit.py`, `test_security_audit.py`, `test_observability_export.py`).

## §28 Frontend (core semantics — Part of width, see also §16)

- **BFF pattern**: `src/app/api/v1/[...path]/route.ts` → `src/lib/bff-proxy.ts` (re-injects Bearer from cookies into upstream); `middleware.ts:27-60` protects segments; cookie lifetimes 15m/30d (`src/lib/session.ts`); 401→refresh→redirect (`src/lib/api.ts`).
- **Client-side business derivations** (recompute money logic in the browser — bypasses server canonical numbers):
  - `(dashboard)/chain/page.tsx:86-92` revenue %-change + hardcoded **SAR 5000** threshold.
  - `components/money-audit/MoneyRecoveryMap.tsx:21-28,50` healthyValue & bar widths from raw audit numbers.
  - `forecast/page.tsx:263-264` 7-day chart heights from forecast series.
  - `ops/page.tsx:85` `capital_at_risk_sar ?? money_at_risk_sar` fallback.
  - `money-audit/page.tsx:295` `data_quality = Math.round(data_quality_score || confidence_score)` — **two different metrics merged**.
  - `money-audit/page.tsx:149` "entered recovery value" in the recovery prompt — user-entered value competes with server-computed one.
  - `dashboard/page.tsx:166,170` avg-basket `toFixed(0)`, profit `toLocaleString`.
  - `components/ActionCenter.tsx:247-288` action success/impact mapping.
  - `suppliers/page.tsx:10` total volume via reduce; `recovery-match/page.tsx:243,523` volume/score math.
  - `feed/page.tsx:103` confidence×100 display.
- **i18n**: static en/ar translations; `landing.parity.test.ts` keeps parity.
- **Test density**: 8 jest unit files + 13 Playwright e2e specs (`frontend/e2e/`); root `e2e/` orphan spec unused by CI.

## §29 Duplicate logic matrix (single-responsibility failures)

| Concern | # impls | Verified sites |
|---|---|---|
| Inventory value | 7 | cost: `audit_core.py:161`, `money_audit_service.py:350`, `branch_memory.py:104`, `business_context.py:130,169`, `chat.py:43`; sell: `analytics_service.py:192,774,1032` |
| Velocity | 3 families | canonical `audit_core.coverage_aware_daily_velocity`; `/30` at `analytics_service.py:172,743,937,1115`, `root_cause.py:36,95,219`, `inventory_orchestrator.py:46`, `product_memory.py:257,539`, `branch_memory.py:119`; SQL `/30.0` in `inventory_agent.py:118-124`, `procurement_agent.py:45-54`, `agent_tools.py:92-106` |
| Days-of-supply | 3 | planner `nazm_planner.py:238`, decisions `decision_engine.py:118`, routers `decisions.py:44`, `context_builder.py:63`, `time_machine.py:110,197`, agents (SQL) — all w/ 999 sentinel |
| Demand forecast | 3 | `forecasting/` package, legacy `prophet_service.py`, `analytics_service.py:920` (+ weekday factors `baseline_provider.py:152`, `forecast.py:208`, `seed.py:135`) |
| Execution orchestration | 4 | `action_executor.py`, `agent_action_executor.py`, `execution_guard.py`+`autonomy_service.py`, `nazm_planner.py` (plan-apply) |
| "execute" endpoint entry | 4 | `actions.py:26`, `money_audit.py:389`, `intelligence.py:616`, `agent.py:296` (autonomy/evaluate) |
| Action-price flag predicate | 2 | `action_registry.py:36` vs `execution_guard.py:91` |
| Margin target | ≥2 | `audit_core.py:27` / `money_audit_service.py:18` = 0.22 vs `evidence_package.py:61,243` = 0.30 |
| Business closure "days_left" sentinel | ≥5 | `decisions.py:44`, `pharmacy.py:67`, `decision_engine.py:70-118`, `nazm_planner.py:238`, `recovery_match_service.py:290`, `time_machine.py:110,197` |

## §30 Hardcoded assumptions & constants (not configuration)

- `TARGET_MARGIN_PCT` 0.22 (`audit_core.py:27`, `money_audit_service.py:18`, `recovery_intelligence.py:16`) vs evidence 0.30 (`evidence_package.py:61,243`).
- Demand multipliers 1.35 (Thu/Fri): `analytics_service.py:920`, `prophet_service.py:251`, shared weekly profile `baseline_provider.py:152` = `forecast.py:208` = `seed.py:135`.
- KPI severity 5000 SAR: `config.py:108`, `audit_engine.py:69,133`, `evidence_package.py:321`, `business_context.py:450`, frontend `chain/page.tsx:86-92`.
- Dead-stock: sale-count `<1` in 30d (`analytics_service.py:256`, `agent_tools.py:106`); velocity floors `NULLIF(...,0.01)` (agents); agent thresholds `<7d` restock (`inventory_agent.py:124`), `<10d` (`procurement_agent.py:54`), margin `<15%` (`margin_agent.py:41`); trend decline 0.95 (`analytics_service.py:313`, `decision_engine.py:353`).
- Confidence floors/caps: 0.90 floor (`config.py:110`, agents 0.9, `autonomy_service.py:118`, rule-bases 0.90/0.95), cap 0.95 (`audit_engine.py:257`, `intelligence_api.py:185,205,259`, `nazm_planner.py:245,567`, `outcome_learning.py:46`).
- 999 sentinel = unknown/no-sales (`decision_engine.py:70-118`, `nazm_planner.py:238`, `time_machine.py:110,197`, `decisions.py:44`, `pharmacy.py:67`, `recovery_match_service.py:290`, `context_builder.py:63`).
- Bounds/limits: notification 5000 chars (`edge_cases.py:341-342`), amount ≤ 999999999999 (`edge_cases.py:159`), subscription "unlimited" 999/999999 (`subscription_service.py:148-151`).
- Ingestion header mis-mapping (§13): `transaction_id→transaction_at`, `business_id→source_transaction_id`, `transaction_type→storage_type`, `location_id→location_name`, `transaction_date` unmapped.
- Default WHATSAPP verifier token still accepts a non-random default unless overridden.

## §31 Silent failure modes & data-integrity risks

- `except → return {}`/`0` patterns returning neutral defaults to business flows (masking). Representative: COALESCE(x,0) on cost/sales (`analytics`, agents); `.get("...",0)` everywhere including ingest mappers.
- `execution_guard.reverify` **fail-open** on rule re-evaluation.
- 999 sentinel means "no data" but is displayed only in dashboards as huge number (planner) — no explicit flag.
- `hostile/unknown location` → fail-closed only for collapse case; unknown locations otherwise silently defaulted.
- Recovery match UPDATE writes without re-asserted party (`recovery_match_service.complete_match`).
- Analytics-learning Celery paths run with **no RLS** (cross-tenant leak vector for aggregates) — highest-severity integrity risk found.
- Chat messages & POS sync logs lack tenant policy (RLS gap).
- Mixed value bases (cost vs sell) mean two "total inventory value" numbers exist and will not reconcile (§15/§29).

## §32 Test architecture, coverage & CI

- **Counts**: 1109 test functions; 15 files under `tests/security/`, 2 under `tests/regression/`, adversarial `tests/adversarial/` (reality-v2 protocol + generator), `tests/load/`, `tests/phase4—6/`, plus `fixtures/` and `regression_data/`.
- **Key suites**: golden-fixture regression (SQL, 28,892 rows + `TestETLIntegration`), adversarial matrix (`test_adversarial_matrix.py`), root-cause assertions, OpenAPI contract golden (`test_openapi_contract.py`), security (RLS/tenant/idor/DLP/chat-no-fabricated-kpis/approval-auth/capsule/output-gate/privacy-firewall/field-encryption/chaos), Celery RLS (`test_celery_rls_tenant_context.py`), deterministic agents, forecasting, business memory, decision safety phase1, closed-loop v7/v8/phase13, e2e happy path.
- **Known suite result at HEAD**: 1190 passed / 3 skipped / 1 xfailed / 1 env flake (celery RLS teardown — passes in isolation).
- **Frontend**: jest unit (bff-proxy, guest-audit-error, middleware, translations parity, universe tokens, RouteGuard) + Playwright public & authed flows.
- **CI**: bandit (gates MEDIUM/HIGH → nosec-approved sites), gitleaks, pytest after `alembic upgrade head`, frontend jest, token-guard; deploy & backup workflows separate.
- **Gaps**: no tests for cross-tenant analytics/learning Celery without-RLS path; no concurrent execution/double-approve test; no guest-audit authz invariance; forecasting multi-location sparse-coverage tests insufficient; no test pins "single source of truth" for value basis (§15). 

---

## Appendix A — Dependency inventory (evidence-grounded)

Runtime (requirements.txt): FastAPI, uvicorn, SQLAlchemy 2 (asyncio), asyncpg, alembic, pydantic v2, pandas, prophet, joblib?, statsmodels? (only where pinned), celery, redis, sentry-sdk, structlog, python-multipart, cryptography, passlib[bcrypt], pyjwt, openpyxl, XlsxWriter?, httpx, aiofiles, openai/llm client, google-* for oauth, tensorflow? (legacy dirs), psutil.
Frontend: next 16.3.0, react, tailwind, jotai/zustand?, shadcn/ui clone, lucide, recharts?, framer-motion, papaparse, zod.
Infra: terraform (GCP), docker compose, systemd.
Legacy/unused surface detected: `prophet_service.py` alongside canonical `forecasting/`; `analytics_service.py` fallback forecasting; stray root `e2e/` Playwright spec.

`UNKNOWN — NOT ESTABLISHED FROM CODE`: exact license/CVE posture per pinned version (the repo ships `cvss` artifacts in CI; not re-derived in this read-only pass).

## Appendix B — Custom-infrastructure pool → OSS replacement candidates

| Custom piece (self-built) | Evidence | Candidate OSS | Verdict |
|---|---|---|---|
| Bespoke analytics/aggregation layer (multi-basis, /30, sell-vs-cost divergence) | §29 velocity/value rows | **DuckDB** (in-process columnar OLAP over the PG mirror or exported parquet) | **Batch 1** (P0) — kills divergence + speeds dashboard/agents |
| 4-way execution orchestration (executors + guard + autonomy + planners) | §23 | **Temporal** (durable workflow runtime; NazmOS rules stay in workflow code) | **Batch 1** (P0) — replaces hand-rolled state machine, gives retries/visibility |
| 3-way forecasting stack (canonical + legacy Prophet + 1.35 fallback) | §18 | **StatsForecast** (pure-Python, fast, permissive license) as canonical provider behind `forecasting/provider.py` | **Batch 1** (P1) |
| RBAC/capabilities on `business.owner_id`+team_members | §9 | Keycloak | **Defer (P2).** Capabilities are business-derived, deeply coupled to tenant model; migration high-risk, value low near-term |
| Secrets handling (env + 1 encrypted col) | §8/§25 | OpenBao | **Defer (P2/P3).** Currently b>1 col, low blast radius; revisit when multi-env secrets expand |
| Observability (structlog+Sentry+Prometheus+OTel) | §27 | already OSS | **Not needed** — no custom replacement warranted |
| Backup (dump + restore drill via systemd) | §25 | pgBackRest/bootstrap | **Not needed now**; acceptable for single Cloud SQL instance |

## Appendix C — NazmOS-core classification (must stay custom)

- Canonical grain & row-hash dedup, tenant model + RLS policies (`ff08`).
- Financial semantics: `audit_core`, `recovery_intelligence`, `money_audit_service` canonical functions → the *definition* of money.
- Capsule/privacy firewall/output gate — the product's unique AI-isolation guarantee.
- Deterministic agent rule library + decision/planner rules + capability matrix (authz).
- POS HMAC webhooks (Foodics/Salla), WhatsApp approve flow, guest-audit UX.
- BFF proxy, session design, client UX — product surface.

## Appendix D — Batch 1 recommendation (exactly 3 replacements)

### D1. Replace bespoke analytics aggregation with a canonical DuckDB-powered financial-semantics core (P0)
- **Current system**: `analytics_service.py` (+ `/30` clones in `root_cause`, `product_memory`, `branch_memory`, `inventory_orchestrator`, agent SQL) compute velocity, dead-stock, inventory value on a *sell-price basis*, and three separate demand-forecast rules — each silently disagreeing with `audit_core` (cost basis, coverage-aware).
- **Why**: §15/§16/§29 divergence is a measured data-integrity bug (two different "total inventory value", two margin targets, three velocities). Rewriting into one module gives a single auditable definition of every KPI.
- **Files**: `analytics_service.py:192,238,256,313,774,1032`, `root_cause.py`, `product_memory.py`, `branch_memory.py`, `inventory_orchestrator.py`, agent SQL (`inventory_agent.py:113-124`, `procurement_agent.py:33-54`, `agent_tools.py`), `evidence_package.py:61,243`, `routers/money_audit.py:882`.
- **Callers**: analytics/dashboard routers, daily summaries task, inventory/emergent agents, forecast router, evidence package.
- **Deps**: duckdb (+ pyarrow export) as optional DEP, behind a thin service module; nothing dynamic replaces probes.
- **Replacement**: new `analytics_core` service that materializes a DuckDB table set (or queries PG once) and produces **the one** value/velocity/classification numberset consumed by routers and agents; `audit_core` and `recovery_intelligence` remain the *canonical math*, analytics_core becomes the *only executor* of it.
- **Integration boundary**: routers + tasks + agents stop computing money themselves; they call `analytics_core`.
- **Risk**: lower (additive module + rewiring callers; sundown old functions), testable against golden fixtures.
- **Preserve**: `audit_core.coverage_aware_daily_velocity`, `recovery_intelligence.classify_inventory`, cost-basis storage.
- **Delete**: duplicate `/30`/`/30.0` sites, sell-basis stock-value returns, `1.35` fallback in `analytics_service.py:920`, 0.30-margin branch of `evidence_package`.

### D2. Replace the 4-way hand-rolled execution orchestration with Temporal (P0)
- **Current**: `action_executor.py`, `agent_action_executor.py`, `execution_guard.py`, `autonomy_service.py`, plus plan-apply in planners; four "execute" entry points (§23).
- **Why**: duplicate state-machine + fail-open guard (§31) + uncoordinated retries across celery vs inline paths; Temporal gives durable retries, visibility, and a single definition of "approved → executed → outcome".
- **Files**: `services/action_executor.py`, `agent_action_executor.py`, `execution_guard.py`, `autonomy_service.py`, `nazm_planner.py` (apply half), `routers/{actions,agent,money_audit,intelligence}.py` execute/apply handlers.
- **Callers**: all approval routes (§22) and any path calling `executor.execute_action`.
- **Deps**: `temporalio` client + worker; single long-running worker (compose) replacing inline executors.
- **Replacement**: workflow per action type; NazmOS rules (capability re-check, reverify, outcome persistence) live **inside** workflow code/hooks, so the runtime is generic OSS and the business remains custom.
- **Integration boundary**: routers submit to Temporal; workflows invoke a *shared* apply-hook library (the current action logic).
- **Risk**: medium (deployment component; fallback inline path retained behind `USE_TEMPORAL` flag during transition).
- **Preserve**: deterministic rule library, capability gates, outcome/impact tables (`executed_actions`, `outcome_feedback`, `impact_ledger`).
- **Delete**: `execution_guard` re-verification fork, duplicated execute handlers, planner apply path.

### D3. Unify forecasting on StatsForecast behind the canonical provider (P1)
- **Current**: canonical `forecasting/` (Prophet) + legacy `prophet_service.py` + analytics `1.35` weekday fallback + hand-rolled weekly profile.
- **Why**: three demand models exist (§18); legacy path and 1.35 rule produce different numbers than canonical cache — inconsistency flows into planners/agents/UI chart heights.
- **Files**: `services/forecasting/{provider.py,prophet_provider.py,baseline_provider.py,cache.py,quality.py}`, `services/prophet_service.py`, `analytics_service.py:920`, `routers/forecast.py:208`.
- **Callers**: forecast router, inventory reports, `nazm_planner`, agents, `sync_runner`.
- **Deps**: `statsforecast`, numpy; `forecast_cache` columns unchanged (`provenance`,`provider`).
- **Replacement**: single StatsForecast provider implementing `forecasting/provider.py`; only provider writes `forecast_cache`; legacy Prophet retained read-only during transition for cache-key compat.
- **Integration boundary**: consumers read `forecast_cache` (unchanged schema); only the provider implementation swaps.
- **Risk**: low (pure-Python, called in sync runner + celery; benchmark vs golden fixtures required).
- **Preserve**: `forecast_cache` provenance, weekly-profile *data* (move to seeded config), quality/coverage gates.
- **Delete**: `prophet_service.py` (after cache migration), `analytics_service.py:920` fallback, hardcoded weekly profile constants.

> **Not in Batch 1**: Keycloak (P2 — high-risk, low near-term value), OpenBao (P3 — low current blast radius), observability (already OSS), backup (adequate).

## Appendix E — Verification checklist & UNKNOWN register

Checklist (all answered with code evidence above):
1. Architecture shipped vs docs — ✅ code-documented (orphan root `e2e/` is the only doc-vs-code mismatch for CI).
2. Data architecture / grain — ✅ §11; item-identity normalization gap registered.
3. Financial truth single-paths — ❌ §15/§29 (three velocity families, two value bases, two margins) — primary Batch-1 driver.
4. Forecasting — ❌ three models exists (§18) — Batch-1 D3 driver.
5. AI isolation — ✅ capsule+gate+advisory-only (§19-20); deterministic runtime confirmed.
6. Security/RLS — ⚠️ verified gaps: chat_messages/pos_sync_logs no policy; analytics+learning tasks no RLS; recovery-match UPDATE weaker; guard fail-open.
7. Execution — ❌ 4 engines = single-responsibility failure (§23) — Batch-1 D2 driver.
8. Infra — ✅ GCP terraform + compose + systemd documented; prod topology UNKNOWN.
9. Migration safety — each Batch-1 item has additive-first strategy; golden fixture & security suites guard.

UNKNOWN register (field-evidence):
- `e2e/` orphan spec maintenance intent.
- Oauth in-memory store multi-instance correctness.
- Live Twilio/Stripe/loyalty adapter cut-through.
- Coarse-grained permission matrix enumeration beyond owner/manage/staff.
- Actual staging/prod deployment topology.
- CVE/license posture per pinned version (CI artifacts not re-derived read-only).
- Item-identity collision resolution lane when two name-synonyms collide.
- Whether analytics/learning No-RLS tasks ever ship real tenants' aggregates to wrong broadcast (risk registered, not yet observed in code tests).

**Batch 2 (future) note**: Keycloak authz migration, OpenBao secrets, pgBackRest replacement, TLS/default-secret hardening (`WHATSAPP_VERIFY_TOKEN` default), SchemaDetector header-map fix.

---

*Report completed during PHASE 0. No production code, tests, or migrations were modified; no dependencies installed; nothing refactored or deleted.*