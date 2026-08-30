# NAZMOS Repository Inventory

Complete inventory of all directories and their purposes, usage status, and evidence.

## Directory Inventory Table

| Path | Type | Purpose | Used By | Status | Evidence |
|------|------|---------|---------|--------|----------|
| `backend/` | Directory | Main FastAPI backend application | Production, Development | ACTIVE | Main entry point `backend/app/main.py`, Dockerfile, requirements.txt |
| `backend/app/` | Package | Core application code | All backend services | ACTUAL | Contains routers, services, models, tasks, middleware, database |
| `backend/app/database/` | Package | SQLAlchemy models, connection, types | All services | ACTIVE | `models.py` (2520 lines), `connection.py` (RLS), `types.py` (UUID compat) |
| `backend/app/routers/` | Package | FastAPI route handlers (29 routers) | API layer | ACTIVE | Auth, businesses, dashboard, inventory, upload, chat, forecast, decisions, money_audit, ops, orgs, subscriptions, adapters, actions, agent, suppliers, pharmacy, whatsapp, partners, admin_backup, oauth, pos_webhooks, orchestrator, recovery_match, compliance, events, intelligence, guest_audit, audits, pilot, health, shariah |
| `backend/app/services/` | Package | Business logic services (80+ files) | Routers, tasks, agents | ACTIVE | Decision engine, business memory, ETL, upload, schema detector, AI gateway, OpenCode brain, money audit, recovery intelligence, agent executor, autonomy, etc. |
| `backend/app/tasks/` | Package | Celery background tasks | Celery worker/beat | ACTIVE | ingestion_tasks, analytics_tasks, audit_tasks, business_memory_tasks, compliance_tasks, event_tasks, forecast_tasks, learning_tasks, pos_sync_tasks, runtime_smoke_tasks |
| `backend/app/intelligence/` | Package | Agent orchestration, tools, registry | Agent router, intelligence API | ACTIVE | Agents, registry, tools |
| `backend/app/middleware/` | Package | FastAPI middleware stack | App startup | ACTIVE | Rate limiter, logging, security headers, idempotency, RLS tenant, Prometheus, API version, deprecation |
| `backend/app/utils/` | Package | Shared utilities | All backend code | ACTIVE | clock, exceptions, logger, logging_context, money, openapi_helpers, problem_details, prompt_sanitizer, saudi_holidays, security, security_validators, startup_checks, tracing |
| `backend/app/schemas/` | Package | Pydantic request/response models | Routers, API contracts | ACTIVE | All API schemas |
| `backend/app/adapters/` | Package | POS integration adapters | POS webhooks | ACTIVE | Foodics, Salla adapters + item_resolver |
| `backend/app/tests/` | Directory | Backend test suite (50+ test files) | CI/CD, development | ACTIVE | Unit, integration, adversarial, security, load, phase tests |
| `backend/alembic/` | Directory | Database migrations (40+ versions) | Production, CI | ACTIVE | Versions from initial schema through Phase 13 learning engine |
| `backend/scripts/` | Directory | Operational scripts | Deployment, health | ACTIVE | runtime_beat_health, runtime_worker_health |
| `backend/monitoring/` | Directory | Prometheus/Grafana configs | Observability | ACTIVE | prometheus.yml, grafana provisioning |
| `backend/nginx/` | Directory | Nginx reverse proxy config | Production | ACTIVE | nginx.conf |
| `backend/Dockerfile` | File | Backend container image | Docker compose | ACTIVE | Python 3.12 slim, requirements install |
| `frontend/` | Directory | Next.js 14 frontend application | Production, Development | ACTIVE | App router, components, hooks, stores, types |
| `frontend/src/app/` | Package | Next.js App Router pages | Dashboard, upload, money-audit, intelligence, etc. | ACTIVE | 20+ page routes under (dashboard) + auth, demo, api |
| `frontend/src/components/` | Package | React components (90+ files) | Pages, UI | ACTIVE | dashboard, free, intelligence, inventory, landing, layout, money-audit, pilot, pwa, ui, upload |
| `frontend/src/hooks/` | Package | Custom React hooks | Components | ACTIVE | useActionCenter, useAuth, useDashboard, useIntelligenceChat, useIntelligenceSummary, useInventory, useMediaQuery, etc. |
| `frontend/src/lib/` | Package | Frontend utilities, API client, i18n | Components, pages | ACTIVE | api.ts, auth.ts, i18n.tsx, schema-detector.ts, translations |
| `frontend/src/stores/` | Package | Zustand state stores | Components | ACTIVE | appStore, authStore, demoStore |
| `frontend/src/types/` | Package | TypeScript type definitions | Frontend code | ACTIVE | api, dashboard, decision, forecast, intelligence, inventory, upload |
| `frontend/public/` | Directory | Static assets | Next.js | ACTIVE | favicon, etc. |
| `frontend/e2e/` | Directory | Playwright E2E tests | CI/CD | ACTIVE | Auth, journey tests |
| `frontend/design-tokens/` | Directory | Design system tokens | UI components | ACTIVE | Colors, spacing, typography |
| `scripts/` | Directory | Root-level operational scripts | Development, CI, data gen | ACTIVE | backup_postgres, check_env, generate_demo_data, load_smoke_test, reality_*, runtime_*, verify_workspace, wait_runtime, v9/v10/v11/v12 experiment scripts |
| `scripts/phase4/` | Directory | Phase 4 experiment scripts | Historical | LEGACY | run_experiment.py |
| `scripts/phase6/` | Directory | Phase 6 pilot scripts | Historical | LEGACY | evaluate_pilot.py, run_pilot_smoke.py |
| `scripts/v9/` - `scripts/v12/` | Directories | Version-specific experiment scripts | Historical experiments | LEGACY | Data generators, evaluators, ground truth, plans |
| `sample_data/` | Directory | Sample CSV fixtures for testing/demo | Tests, demos | ACTIVE | v9, v10, v11, v12 sample data + reality fixtures |
| `sample_data/v9/` - `v12/` | Directories | Version-specific sample data | Experiment runners | LEGACY | Business manifests, inventory, sales, suppliers |
| `reality_fixture/` | Directory | Reality test input fixtures | Reality test runner | ACTIVE | reality_inventory.csv, reality_sales.csv |
| `reality_test_output/` | Directory | Reality test outputs | Audit verification | ACTIVE | business_context_full.json, playwright journey, shots |
| `results/` | Directory | Experiment results | Historical | LEGACY | v9, v10, v11, v12 results + phase1_baseline |
| `infrastructure/` | Directory | Terraform infrastructure | Production deployment | ACTIVE | main.tf, outputs.tf, variables.tf |
| `deployment/` | Directory | Deployment configs | Production | ACTIVE | (empty in current scan) |
| `docs/` | Directory | Documentation | Team reference | ACTIVE | previews, codebase-audit (this audit) |
| `e2e/` | Directory | Root-level E2E configs | Playwright | ACTIVE | (empty in current scan) |
| `uploads/` | Directory | File upload storage (local) | Development | ACTIVE | Used by local storage backend |
| `backend/uploads/` | Directory | Backend upload storage | Local backend | ACTIVE | Mounted in docker-compose |
| `backend/tmp/` | Directory | Temporary files | Runtime | ACTIVE | v12_ai_calls.jsonl, v9_ai_calls.jsonl |
| `backend/nazmos_smoke.db` | File | SQLite dev database | Development | ACTIVE | Created by dev mode |
| `.github/workflows/` | Directory | GitHub Actions CI/CD | CI/CD | ACTIVE | (not examined in detail) |

## Status Legend

- **ACTIVE**: Currently used in production or development, referenced by running code
- **LEGACY**: Superseded by newer implementation but still referenced or preserved for history
- **DEAD**: No references found, not reachable from any entry point
- **TEST-ONLY**: Used exclusively by test code
- **DEVELOPMENT-ONLY**: Used only by development tooling/scripts

## Key Observations

1. **Massive service layer**: 80+ service files in `backend/app/services/` - indicates significant business logic but potential for duplication
2. **Version-specific scripts**: v9-v12 experiment scripts appear to be historical/legacy (not referenced by current code)
3. **Comprehensive migration history**: 40+ Alembic migrations tracing full schema evolution
4. **Frontend well-organized**: Clear separation of pages, components, hooks, stores, types
5. **Test coverage extensive**: 50+ test files covering unit, integration, adversarial, security, load, and phase-specific tests
6. **Dual AI integration**: Both `ai_gateway.py` (high-level) and `opencode_brain.py` (CLI subprocess) exist
7. **Multiple decision engines**: Legacy `DecisionEngine` class + Phase 4 `generate_decision()` function
8. **Memory architecture**: BusinessMemory + Event engine + Projectors pattern implemented