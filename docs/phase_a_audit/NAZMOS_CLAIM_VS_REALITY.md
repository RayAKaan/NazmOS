# NazmOS — Claim vs Reality

> Section 33 of the mission brief. Each claim is rated: `VERIFIED` (code + runtime-consistent), `PARTIAL` (code only, needs external prereq), `NOT VERIFIED` (no in-repo evidence), or `FALSE`.

| Claim | Evidence found | Reality |
|-------|---------------|---------|
| "NazmOS AI recommends actions" | `llm_orchestrator.py`, `ai_reasoning.py`, `ai_challenge.py`, `opencode_brain.py` | `VERIFIED` as **advisory** layer; default mock unless LLM keys set |
| "OpenCode integration" | `services/opencode_brain.py` — external CLI subprocess w/ timeout + validation | `PARTIAL` — external CLI + provider key required; fail-closed |
| "AI executes actions autonomously" | Every AI path goes through `decision_engine` / `nazm_planner` gate + approval (`agent_actions`), execution via `agent_action_executor` | `FALSE` — by design AI never executes alone |
| "Business Memory" | `business_memory.py`, `business_context.py`, `memory` tables (projectors from event engine) | `VERIFIED` (see Memory section) |
| "Money audit" | `money_audit_service.py`, financial measures, `Numeric`/Decimal discipline | `VERIFIED` |
| "Financial Impact / Recovery Opportunity / Expected / Actual Recovery" | models + audit service dedupe legacy cols | `VERIFIED` (see Financial Audit) |
| "Foodics integration" | `adapters/foodics.py`, `pos_webhooks.py`, HMAC | `VERIFIED` (code), `NOT VERIFIED` (runtime, no creds) |
| "Salla integration" | `adapters/salla.py`, `pos_webhooks.py` | `VERIFIED` (code), `NOT VERIFIED` (runtime) |
| "WhatsApp approval" | `whatsapp_bridge.py`, `routers/whatsapp.py` | `VERIFIED` mock; `NOT VERIFIED` live (needs token) |
| "Outcome learning" | `outcome_learning.py`, `learned_outcomes`, `outcome_feedback`, `learning_adjusted_action` | `VERIFIED` |
| "Celery scheduled jobs" | `celery_app.py`, tasks; `USE_CELERY=False` default, enabled in some compose | `PARTIAL` — runs if flag set + broker present |
| "Redis" | `cache_service.py`, `USE_REDIS` flag | `PARTIAL` — disabled by default |
| "Tenant isolation via RLS" | `connection.py` `SET LOCAL app.current_tenant_id`, app role, `enforce_tenant_filter` | `VERIFIED` |
| "Role-based permissions" | RBAC middleware, `permission_definitions`, `capabilities_service` | `VERIFIED` (see Security) |
| "Recovery match (surplus between stores)" | `recovery_match_matcher.py`, `recovery_intelligence.py` | `VERIFIED` code; outcome dependant on adjacent-store data |
| "Baseline / pilot mode" | `pilot_mode.py`, `pilot_readiness.py`, `pilot_baselines` | `VERIFIED` (Phase 6) |
| "Simulation / what-if" | `simulation_engine.py`, intelligence `simulate` | `VERIFIED` |
| "Forecast (Prophet)" | `prophet_service.py` | `VERIFIED` Python-only path |
| "Backup / DR" | `backup_service.py`, admin_backup router, scripts | `VERIFIED` |