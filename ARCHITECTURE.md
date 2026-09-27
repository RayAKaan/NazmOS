# ARCHITECTURE.md

**How NazmOS actually fits together today (verified at HEAD `208ca04` + working tree).**
Evidence labels: [V]=verified, [H]=historical, [I]=inferred, [B]=blocked, [NP]=not present.

## 1. Layering at a glance

```
HTTP (FastAPI app.main)                     [V]
  routers: auth, inventory, dashboard, money_audit, recovery_match,
           agent, chat, intelligence, pos_webhooks, whatsapp, pilot, audits ...
  middleware: TenantContextMiddleware (RLS), security_headers, logging      [V]
      │
      ▼
services/
  intelligence_api (analyze/reason/predict/plan/execute/observe/...)
  intelligence_api_client (IntelligenceAPIClient wrapper)                  [V]
  ab_decision_framework.deterministic_decision_for_item (L91)              [V]
  ai_reasoning / ai_challenge  → llm_orchestrator (Groq|Gemini|mock)       [V]
  ai_gateway.reason  → opencode_brain  (NO production callers today)       [V]
  audit_core.coverage_aware_daily_velocity (canonical velocity)            [V]
  money_audit_service, recovery_match_service, outcome_learning, ...
  analytics/* (in-memory DuckDB engine, scoped, fail-closed)               [V]
      │
      ▼
orchestration/  (single execution layer)                                   [V]
  runner: run_manual_action | run_agent_approval | run_agent_rejection
          | run_simulated  → _dispatch (runner.py:177-191)                 [V]
  workflows (precheck → constraints → idempotency → apply → record)        [V]
  contracts.py (ExecutionRequest, 2C-A serializers)                        [V]
  temporal/{workflows, activities, policies, schedules, worker}            [V]
  startup_checks.validate_temporal (fail-closed)                           [V]

storage:
  PostgreSQL (RLS via SET LOCAL role + tenant ctx)                         [V]
  Redis (limiting/cache)                                                   [V]
  Temporal server (durable execution) — reachable, container "unhealthy"   [V]
```

## 2. The deterministic financial core (money-critical, MUST stay deterministic)

- `audit_core.py` — canonical metrics: `gross_margin_pct` (:44), **`coverage_aware_daily_velocity` (:58-75)**, `analyze_product` (uses velocity at :172). Semantics verified: coverage `None → /30` legacy; qty>0 & coverage<=0 → /1; zero qty → 0; qty/coverage otherwise. [V]
- `money_audit_service.py:345` — uses canonical velocity (converged). `DEAD_STOCK_DAYS = 45` (:20). [V]
- `recovery_match_service.py:145,297` — canonical velocity (converged). [V]
- `root_cause.py:52` — re-applies canonical over SQL `/30` (patched). [V]
- NOT yet converged (inline `/30` or bare division): `audit_engine.py:173`, `inventory_orchestrator.py:46`, `nazm_planner.py:486`, `intelligence_api.py:233`, `evidence_package.py:188` (synthetic-only, deliberate), `root_cause.py:38/110` (raw SQL). [V] — see MIGRATION_MATRIX notes & Phase 1 (2B completion) work.
- Dead-stock rule conflict: `DEAD_STOCK_DAYS=45` constants vs 30-day scans (`audit_engine.py:127`, `goal_service.py:79`, analytics 30-day default; canonical WS5 rule "< 1 unit sold in window" at `analytics/contracts.py:75`). [V]

## 3. AI / intelligence surface (audited truth)

Three distinct AI surfaces exist:
1. **Chat/agent/analyze path (production, live):** routers → `IntelligenceAPIClient.reason/analyze` → `intelligence_api` → `ab_decision_framework` (+ optional `reason_about_item` / `ai_challenge`) → `llm_orchestrator` (Groq `llama-3.3-70b-versatile`, Gemini `gemini-2.5-flash-lite`, provider order `groq,google,mock`; `USE_MOCK_LLM` fallback). Per-request models recorded in `ai_reasoning_requests` (provider column at `models.py:2428`). DLP: prompt builders use `capsule.for_prompt()`; `llm_rate_limiter` enforces provider ceilings. [V]
2. **ai_gateway.reason (built, dormant):** policy kill-switch + `GLOBAL_AI_BUDGET` + `ReasoningCapsule` (privacy firewall) + `opencode_brain` transport + durable `ai_reasoning_requests` audit. **Zero production callers** (only test `test_ai_isolation.py:350`; `pilot.py` imports just `budget_snapshot`). [V]
3. **V8/V11 experimental + money-audit counterfactual:** experiment endpoints and the A/B/C counterfactual router reach OpenCode/AI for research only. [V]

Security stack: `security/{ai_policy, capsule, privacy_firewall, output_gate, ai_adapter, master_prompt}.py`. Output contract normalized to `{decision, confidence, reasoning, evidence_ids, risk_flags, alternative_decision, challenge}`. [V] Master system prompt is static, DLP-clean, delivered as system role via runner `/app/agents/nazmos-brain.md` (`opencode run --pure --agent nazmos-brain`). [V] Capsule carries **no business_id** — tenant column resolved from RLS context (capsule.py design, ai_gateway.py:123-126). [V]

## 4. Execution & governance (unchanged by Jev design)

- Single dispatcher: `runner.py:177-191` `_dispatch` — `USE_TEMPORAL` → `_temporal_run` else `_local_run` (tests/CI only; `config.py:343-349` rejects `USE_TEMPORAL=false` in production). `_temporal_run` raises `TemporalExecutionError` on failure (runner.py:290-296) — **no fallback**. [V]
- Startup fail-closed: `startup_checks.py:32-35` raises on Temporal ping failure; `config.py:404-405` auto-off only for SQLite when env unset. [V]
- Workflow step order (local `workflows.py` and Temporal `ManualActionWorkflow`/`AgentApprovalWorkflow`): capability (precheck) → constraints → idempotency (SHA-256 `execution_key`, keys.py) → apply → record. Agent flow adds approve → executing → terminal → best-effort learning. [V]
- `precheck.py:18-37`: capability re-validated at execution (`user_has_capability(can_approve_actions)`). [V]
- `autonomy_service.py` dial: 0 = inform-only; 1–94 = pending_approval; 95–100 = auto-execute only if guardrails pass. DEFAULTS: restock 50, pricing_increase 20, pricing_decrease 30, cash_alert/staff_schedule/expense_decline/recovery_match/discount 0. [V]
- `execution_guard.py:29-36`: blocked verdicts `CODE_TENANT_MISMATCH | CODE_INSUFFICIENT_PERMISSION | CODE_CONSTRAINT_VIOLATION | CODE_EXECUTION_PREVENTED`, persisted to `constraint_blocks`. [V]
- Contract (2C-A) `contracts.py`: `ExecutionRequest` is a frozen dataclass carrying `business_id, action_type, entity_type, entity_id, payload, previous_state, new_state, source="manual", execution_key, decision_id, user_id, plan_id, action_id, note, decided_by, schema_version, decision_type`. **Notably: no `autonomy_dial` field** — autonomy lives on the business model (`autonomy_dial_at_creation`, models.py:1156). [V]
- **No AI/model output triggers business actions anywhere today.** All actions flow through the dispatcher. [V]

## 5. Outcome feedback & learning (2C-B)

- `outcome_feedback_contract.py`: schema version + statuses CONFIRMED/PARTIAL/FAILED/UNKNOWN/REJECTED; `CANONICAL_FEEDBACK_FIELDS`; serialize/deserialize; idempotency key derivation (:171-183). [V]
- `outcome_learning.py`: `record_unified_outcome` (:219) writes `learned_outcomes` (ON CONFLICT DO UPDATE) and `outcome_feedback` (ON CONFLICT DO NOTHING); consumers: `orchestration/record.py:307-308`, `runtime.py:219-222`, `learning_reconciliation.py:27-29`, `routers/audits.py:314`. The learning loop consumes **verified outcomes of executed actions** — never raw model output. [V] — this is the correct hook for Jev evidence/confidence recalibration.

## 6. Temporal & RLS (verified details)

- `temporal/workflows.py`: `ManualActionWorkflow`, `AgentApprovalWorkflow`, `SimulatedWorkflow` + Phase-2A generic/bulk one-activity workflows; `WORKFLOWS` registry. [V]
- `temporal/activities.py`: 29+ real `@activity.defn` adapters over canonical business fns (e.g. `apply_restock`, `apply_price_change`, `record_agent_terminal`, `record_terminal_outcome`, `run_daily_full_audit`, `run_nightly_recovery_match_scan`). [V]
- `temporal/worker.py`: `build_worker`, entrypoint `python -m app.orchestration.temporal.worker`. [V]
- `temporal/schedules.py`: idempotent Temporal schedules replacing Celery-Beat ops (DEFAULT_SCHEDULES; CLI). [V]
- RLS: `middleware/rls_tenant.py` `TenantContextMiddleware` sets tenant ContextVar only after token-validated auth resolution (lines 76-154); ContextVar `_rls_tenant_id`; `connection.py:_set_rls_context` (:179-197) issues `SET LOCAL app.current_tenant_id` and `SET LOCAL ROLE "nazmos_app"`; `DATABASE_APP_ROLE` from config/env (`.env.example:21`), literal `nazmos_app` required in prod docs. [V]

## 7. Analytics (DuckDB boundary)

- `app/analytics/*` — one scoped in-memory DuckDB engine per computation, streams tenant-scoped rows, closes fail-closed. Raw aggregates only; semantics live in `analytics/metrics.py` (`coverage_aware_daily_velocity`, `dead_stock_total`, `dead_stock_rows`) on top of `ItemFact`/`ItemKPI`. `CAST(inv.business_id AS TEXT)` keeps it DB-agnostic. [V]

## 8. Where a Jev transport fits (structural conclusion)

1. **Natural insertion point (shadow mode):** `ab_decision_framework.deterministic_decision_for_item` (L91) is the single deterministic decision funnel — Jev shadow evaluators attach here, comparing Choice/Score/Noul vs deterministic decision, deterministic wins. [V]
2. **Policy/choke point:** extend `ai_gateway.reason` with a `systemone` transport (ai_adapter) OR add `jev` capability alongside `opencode_brain`. Because the gateway currently has no production callers, this is greenfield and does not disturb Groq/Gemini chat. [V]
3. **Audit/evidence:** persist Jev answers via `record_ai_reasoning_request` (capsule hashes, no raw payload) and via `DecisionEvidence`-style structures; consumption for learning via `outcome_feedback_contract` (verified outcomes only). [I]
4. **Execution:** Jev never executes; Temporal dispatcher unchanged. [V]
5. **Governance:** owner/Shariah gates stay deterministic (`pricing.owner_band_eligibility`, `governance.shariah_review_triage` never delegated). [V]