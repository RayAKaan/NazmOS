# Phase 1 — Repository Audit Map

Date: 2026-08-19. This is the *internal inspection result* the Phase-1 brief asked for,
before any implementation decisions. The repo is materially more advanced than the brief
assumes; the map below distinguishes what already works from what is actually missing.

## What already works (do NOT rewrite)

| Area | Where | Status |
|---|---|---|
| Nazm Agent OS (attention feed, approval queue, autonomy dial 0–100, approve/reject, dry-run, scan trigger) | `routers/agent.py`, `nazm_planner.py` | ✅ full |
| Canonical **action** model w/ full lifecycle + outcome tracking | `AgentAction` + `AgentActionStatus/Type` (models.py:1005) | ✅ full |
| **Policy engine** (dial → inform/draft/auto-execute, guardrails: ceiling_sar, price %, quiet hours, 2FA, confidence≥0.90 gate) | `autonomy_service.py` (319 ln), `AutonomyPolicy` model | ✅ full |
| Agent **tools** (read-only: inventory, dead-stock, transfers, margin) | `agent_tools.py` | ✅ partial (4 tools) |
| Deterministic **action executors** (pricing update, restock→purchase order) | `agent_action_executor.py` | ✅ full |
| **Model provider abstraction** (Groq + Gemini + mock, `LLM_PROVIDER_ORDER`, circuit breaker, normalized OpenAI shape) | `llm_orchestrator.py` (333 ln), config | ✅ full — do NOT add a new one |
| Specialized agents (inventory/pricing/supplier/finance/compliance) | `intelligence/agents/*` | ✅ basic (propose-only) |
| Intelligence API (analyze/predict/explain/plan/simulate/reason) + decisions + outcome feedback | `intelligence_api.py`, `decision_engine.py`, `IntelligenceDecision`, `OutcomeFeedback` | ✅ full |
| Execution engine + jobs | `execution_engine.py`, `ExecutionJob` | ✅ full |
| Event engine + 15 seeded event types + subscriptions | `event_engine.py`, `event_registry_seed.py` | ✅ full |
| Money Audit (computation, generation, actions, WhatsApp/print summary) | `money_audit_service.py` (656 ln), `MoneyAudit`, `MoneyAuditAction` | ✅ full |
| Recovery Match | `recovery_match_service.py`, models, router | ✅ full |
| Compliance radar (read-only) | `routers/pharmacy.py` `/recalls` (SFDA), `routers/shariah.py` pricing-ethics, `routers/compliance.py` GDPR export/delete | ✅ full — satisfies brief §13 |
| RBAC / RLS / tenant isolation / feature flags / idempotency / audit log | `middleware/*`, `AuditLog` | ✅ full |

## What is partially implemented (extend, don't rewrite)

- **Agent "runtime"**: `BaseAgent.propose()` is the whole contract. Missing identity/objective/
  tools/policies/permissions/verification/budget surface (brief §5).
- **Tool layer**: 4 ad-hoc tools, no registry, no risk classification, no permission binding (brief §7).
- **Continuous audit**: event engine exists but nothing maps event types → audit re-runs (brief §11).

## What is genuinely missing (implement)

1. **Canonical `Finding` model** — no unified finding; only money-audit actions and agent actions.
2. **Audit lifecycle** — `MoneyAudit.status` is `generated/reviewed/sent/archived`, not
   PENDING/RUNNING/COMPLETED/FAILED; no `AuditRun` entity; no **domain registry** (brief §2–4).
3. **Recovery Agent** — no `recovery_agent.py` (brief §12).
4. **Risk classification** on the policy engine (low/medium/high → auto/draft/approve) (brief §8).

## What should NOT be touched yet

- `llm_orchestrator.py` (provider abstraction already exists — replacing it would churn 3 test suites).
- `money_audit_service.py` internals (reuse via adapter, don't fork logic).
- RLS/RBAC/idempotency/audit-log (verified working; 374 tests pass).

## Duplication to consolidate (not rewrite)

- `MoneyAuditAction.status` and `AgentAction.status` are two parallel action lifecycles.
  The new `Finding` model is the canonical umbrella; both can link to it via `source` + `entity_id`.
