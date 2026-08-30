# NazmOS — Codebase Audit (Master Report)

> Consolidates `NAZMOS_*` documents in `docs/codebase-audit/`. Evidence-based; source code is the authority. Companion docs: `NAZMOS_REPOSITORY_INVENTORY.md`, `NAZMOS_CUSTOMER_JOURNEY.md`, `NAZMOS_CUSTOMER_JOURNEY_CODE_LEVEL.md`, `NAZMOS_DATA_FLOW.md`, `NAZMOS_DATABASE_ARCHITECTURE.md`, `NAZMOS_TENANT_ISOLATION.md`, `NAZMOS_AI_ARCHITECTURE.md`, `NAZMOS_INTEGRATIONS_AUDIT.md`, `NAZMOS_DEAD_CODE_AUDIT.md`, `NAZMOS_CLAIM_VS_REALITY.md`.

## 1. Executive Summary

**NazmOS is a real, substantially-built product.** It is a FastAPI + Next.js multi-tenant retail-recovery platform (KSA focus) with a PostgreSQL RLS data layer, a 70+ table schema, a 29-router API, event-driven business memory, a deterministic financial engine (money audit), a rule-based "Nazm Planner," a bounded decision engine, an outcome-learning loop, WhatsApp/POS integrations, and an advisory AI layer. It is **not a shell or a single-file demo** — there is deep, layered, and largely coherent implementation across `backend/app/`, `frontend/`, tasks, and migrations.

**Critical honesty:**
1. **AI is optional and advisory.** Out of the box (`USE_MOCK_LLM`/no keys) the LLM layer streams canned mock responses; everything that matters is deterministic. The "OpenCode" integration is a fail-closed subprocess to an external CLI that requires a host install + provider key — `PARTIAL`.
2. **Money math is disciplined.** `Decimal`/`Numeric(12,2)`/**Numeric(14,2)** throughout; no float accounting; legacy financial columns coexist but are mapped in the audit services.
3. **Tenant isolation is real** (RLS via `SET LOCAL app.current_tenant_id` + app role), though two SQL-paths with explicit `business_id` defense-in-depth were noted as worth hardening.
4. **Foodics/Salla are webhook-only**, HMAC-signed, adapter code verified but runtime untested — report them `NOT VERIFIED` (no credentials in-repo).
5. There is **significant experiment sprawl** (`scripts/v9..v12`, `sample_data/v9..v12`) and a handful of **apparently-dead tables** — future engineering debt, not runtime blockers.

## 2. System Scorecard

> 1–10, based on code evidence only.

| Dimension | Score | Basis |
|---|---|---|
| Architecture clarity | 8 | Layered, coherent; event engine + projectors + memory |
| Data model depth | 9 | 70+ tables, constraints, RLS, migrations |
| Money safety | 9 | Decimal discipline, tight numerics, audit trails |
| Multi-tenancy | 8 | RLS core strong; edge SQL paths need review |
| Deterministic intelligence | 8 | Money audit, recovery intelligence, decision engine, planner |
| AI layer | 4 | Advisory-only mock-by-default; OpenCode external/unverified |
| Integrations (POS/WhatsApp) | 5 | Code present; runtime unverifiable without credentials |
| Execution & outcome loop | 7 | Approval→executor→LearnedOutcome→KG real |
| Frontend maturity | 7 | Rich dashboard/audit/chat surfaces, AR/EN, PWA |
| Operational maturity (Celery/Redis/DR) | 4 | Flag-gated; defaults off; backup exists |
| Test depth | 8 | Phase-gated unit/contract tests + runtime harnesses present |
| **Overall** | **7.0 / 10** | Real product; AI claims need honesty in docs |

## 3. Technical Debt Ranking (highest risk first)

1. **Financial-measure duplication**: `money_at_risk_sar`/`expected_recovery_sar` (legacy) vs `capital_at_risk_sar`/`recoverable*` — silent drift risk despite normalization services.
2. **Two execution engines**: `execution_engine.execute_job` is explicitly simulated (`"simulated": True`) but `agent_action_executor` executes real deterministic handlers. Docs could mislead.
3. **Unused tables** (`recipes`, `parts_compatibility`, `enabled_modules`, `pricing_rules`, `pricing_recommendations`, `notifications`, `reports`, `executed_actions`, `analytics_cache`, `team_invitations`) → schema drift/migration bloat.
4. **AI budget in-memory only** — resets on restart; multi-worker overage.
5. **External `opencode` CLI dependency** — unverified, fail-closed.
6. **Flag-gated operational infra** (Celery/Redis) — scheduled features silently off in default compose.
7. **Experiment directories** inflate repo + confuse CI.

## 4. Top Risks

- **AI narrative overreach**: "AI-driven" marketing vs mock/default-deterministic reality is the #1 credibility risk; docstrings already hedge ("simulated", "fallback") — keep it public.
- **Runtime integration claims**: Foodics/Salla/WhatsApp live paths are unverified — a client demo hitting live mode will fail unless credentials set.
- **RLS edge cases**: any SQL bypassing the RLS context (`_rls_tenant_id`) without explicit filtering leaks cross-tenant rows; defensive `business_id` clauses exist but audits should systematically grep raw-SQL paths.
- **Data-shape drift**: CSV → ETL → normalizer strictness (v12) indicates past ingestion discrepancies; keep `master_expected` style fixtures.
- **Dead tables relied upon unknowingly**: e.g., if a future migration drops `executed_actions` while a report still reads it.

## 5. Key Numbers

- Backend: FastAPI, 29 routers, ~100+ services, 100k-row upload cap, HMAC POS, JWT auth, Celery beat schedule (daily summaries/forecast/learning/audit).
- DB: ~70+ tables, 40+ Alembic migrations, UUID keys + SQLite-compat types, RLS tenant context.
- Frontend: Next.js App Router; dashboard/upload/money-audit/intelligence/orchestrator/inventory.
- Money: `Decimal` + `Numeric(12,2)`/`Numeric(14,2)`; financial measures: Inventory → Capital→Revenue→Gross Profit at Risk → Recoverable Low/High → Expected/Actual Recovery.

## 6. Master Data-Flow (one-line synthesis)

```
Upload/POS → ETL(normalize→items→transactions[dedup row_hash]→summaries→forecast)
  → Money Audit / Recovery Intelligence (deterministic findings + financial impact)
  → Nazm Planner + Decision Engine (bounded recommendations)
  → AI advisory (validated; optional; falls back deterministic)
  → AgentActions (pending_approval) → web/WhatsApp approval
  → Execution (guard + deterministic executor or MANUAL)
  → Outcome Learning (LearnedOutcome + OutcomeFeedback) → Knowledge Graph → future context
```

## 7. 26 Final Questions (answered)

1. **Is NazmOS real?** Yes — deep, multi-phase implementation across backend/frontend/db/tasks.
2. **Is it a solo-project artifact?** Evidence of 12+ phases (v2→v12) → long experiment lineage, single-team style.
3. **Where do users originate?** Dashboard authed orgs (auth/businesses) + `guest_audit` route; pilot mode.
4. **Does AI output real decisions?** No — AI output is advisory + validated; NazmOS/deterministic engines rule.
5. **Is OpenCode actually calling anything?** Not verifiable; requires external CLI + key; fail-closed.
6. **Are financials trustworthy?** Yes — Decimal/Numeric discipline, audit columns, impact ledger.
7. **Is tenant isolation enforced?** Yes via RLS; defense-in-depth reviewer flagged for raw-SQL paths.
8. **Fire-and-forget features?** `recipes`, `parts_compatibility`, `pricing_rules`, `pricing_recommendations`, `notifications`, `reports`, `executed_actions`, `analytics_cache`, `team_invitations` — apparent dead weight.
9. **POS integrations real?** Code real; runtime unverified (no creds).
10. **Can WhatsApp approvals work?** Mock by default; live needs Meta token; deep-link fallback ensures delivery path.
11. **Is money lost if backend dies mid-action?** Action states are DB rows with idempotency; execution guard + outcome ledger; graceful.
12. **Where does actual revenue come from?** Subscriptions (Stripe-ish), merchant activation; CRM/POS contracts; not AI credits.
13. **Who owns the intelligence?** Deterministic engines own; AI is presentation.
14. **Is the learning loop real?** Yes — LearnedOutcome/OutcomeFeedback/KG projections; rejection-aware.
15. **Any simulated components pretending to be prod?** `execution_engine.execute_job` is explicitly simulated (keep out of prod claims).
16. **Scaling boundaries?** 100k-row ETL cap; in-memory AI budget; SQLite demo fallback; real path is Postgres.
17. **Config trouble?** `USE_CELERY/Redis/Mock` flags decide behavior; defaults deliberately cheap.
18. **Frontend/backend contract drift?** Shared KPI/audit types; i18n; PWA; potential drift in action-type enum strings.
19. **Can anyone access others' data?** DB RLS + business_access/RBAC middleware mitigate; raw-SQL needs audit.
20. **Is there failure handling?** Extensive (§26 failure recovery: source-stock fail-closed transfer, WhatsApp fallback, webhook 4xx mapping, circuit breaker for LLM).
21. **Is testing real?** Phase-gated test suites (phase1..13), contract/chaos, runtime E2E harnesses, reality/Playwright scripts.
22. **What is DEAD?** Listed above + experiment dirs.
23. **What is LEGACY/SUPERSEDED?** v9–v12 experiment data/scripts; legacy financial cols; `executed_actions`.
24. **Is frontend production-like?** Yes — polished dashboard, audit UX, orchestrator, AR/EN, PWA.
25. **Biggest single risk?** Credibility gap between "AI financial assistant" claims and deterministic/mock reality.
26. **Overall maturity?** ~7/10 — production-shaped core; AI + integrations + ops flags need hardening before revenue-app timing.

## 8. Notable Router & Service Highlights

- **Money audit**: `GET /money-audit/…` → `money_audit_service` + `recovery_intelligence` (financial risk classification) + TopDecisions / TimeMachine / DecisionComparison / DoNotDoThis UI.
- **Recovery match**: nearby-store surplus matching (`recovery_match_matcher.py`), approval-gated contact reveal.
- **Chat**: `/chat` streams via `llm_orchestrator` (mock default) with `AGENT_TOOLS` deterministic tooling.
- **Orchestrator**: cross-module scan runner combining planner + optimizer + intelligence.
- **Admin backup**: Postgres backup/restore/retention (`backup_service.py`).
- **Ops**: health, infra status, pilot readiness; guest audit for anonymous uploads.

## 9. Reading Set (deep-dive starting points)

`backend/app/main.py` → `config.py` → `database/connection.py` + `models.py` → `services/money_audit_service.py` + `recovery_intelligence.py` → `services/nazm_planner.py` + `decision_engine.py` → `services/agent_action_executor.py` + `outcome_learning.py` → `services/llm_orchestrator.py` + `ai_response_validator.py` → `pos_webhooks.py` + `adapters/*` → `celery_app.py` + `tasks/` → `frontend/…/(dashboard)`.