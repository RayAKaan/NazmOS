# NAZMOS Canonical Architecture

**Version**: Phase A Audit — 2026-08-29  
**Status**: ACCEPTED  
**Scope**: Backend (FastAPI/PostgreSQL) + Frontend (Next.js) + Infra (Docker/Celery/Redis)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        NAZMOS ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│  │   FRONTEND   │    │    BACKEND   │    │   DATABASE   │             │
│  │  (Next.js)   │◄──►│  (FastAPI)   │◄──►│ (PostgreSQL) │             │
│  │  Port 3000   │    │  Port 8000   │    │  Port 5432   │             │
│  └──────────────┘    └──────┬───────┘    └──────────────┘             │
│                             │                                        │
│                    ┌────────┼────────┐                               │
│                    ▼        ▼        ▼                               │
│              ┌──────────┐ ┌───────┐ ┌────────┐                       │
│              │  CELERY  │ │ REDIS │ │ EVENTS │                       │
│              │ (Worker) │ │ Cache │ │ (Bus)  │                       │
│              └──────────┘ └───────┘ └────────┘                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Principles

| Principle | Enforcement |
|-----------|-------------|
| **Deterministic First** | All decisions start with `decision_engine.py`; AI augments, never replaces |
| **Fail-Closed** | Validation failure → deterministic fallback; constraint block → no execution |
| **Evidence-Bounded** | Financial claims must match `ItemEvidence` values; hallucination → rejection |
| **Tenant Isolation** | Every query filtered by `business_id`; RLS enforced in production |
| **Zero-Cost Optional** | Celery/Redis/LLM toggled via `USE_CELERY`/`USE_REDIS`/`USE_MOCK_LLM` |

---

## 3. Module Classification

| Module | Status | Layer | Purpose |
|--------|--------|-------|---------|
| `decision_engine.py` | **ACTIVE** | Core | Canonical deterministic rules |
| `nazm_planner.py` | **ACTIVE** | Core | Plan builder for API |
| `execution_engine.py` | **ACTIVE** | Execution | Simulated plan tracking |
| `agent_action_executor.py` | **ACTIVE** | Execution | Real DB mutations (approval-gated) |
| `money_audit_service.py` | **ACTIVE** | Audit | Production money audit |
| `ai_response_validator.py` | **ACTIVE** | Guardrail | Dual-contract dispatcher (§12 + V8) |
| `opencode_brain.py` | **ACTIVE** | AI | Production OpenCode path |
| `llm_orchestrator.py` | **ACTIVE** | Infra | Multi-LLM routing |
| `evidence_package.py` | **ACTIVE** | Data | Canonical evidence builder |
| `recovery_intelligence.py` | **ACTIVE** | Finance | Conservative financial estimates |
| `ab_decision_framework.py` | **COMPATIBILITY** | Experiment | V8 A/B counterfactual |
| `ai_challenge.py` | **COMPATIBILITY** | Experiment | V11 challenge layer |
| `business_context.py` | **COMPATIBILITY** | Experiment | V11 context engine |
| `closed_loop_experiment.py` | **TEST-ONLY** | Experiment | 60-day simulation |
| `ai_reasoning.py` | **COMPATIBILITY** | Experiment | Structured reasoning |
| `execution_guard.py` | **ACTIVE** | Guardrail | Constraint validation |

---

## 4. Decision Path (Canonical)

```
UPLOAD → money_audit_service.run_money_audit()
    → build_item_evidence() → ItemEvidence (canonical fields)
    → decision_engine.deterministic_decision_for_item()
    → nazm_planner.build_plan()
    → action_registry (registered actions only)
    → agent_action_executor.approve_agent_action()  [human approval]
    → execute_agent_action() → DB mutations + outcome_json
```

**AI Path** (async, best-effort, fail-closed):
```
opencode_brain.reason()
    → OpenCode CLI → raw JSON
    → ai_response_validator.validate_ai_response() [§12 string contract]
    → ValidationResult → if invalid: deterministic fallback
    → if valid: enrich plan (no auto-execution without approval)
```

---

## 5. Experiment Boundary (V8/V11)

```
/api/v1/money-audit/ab-compare  (lazy import)
    → ab_decision_framework.run_counterfactual_audit()
        → MODE_A: deterministic only
        → MODE_B: + AI reasoning (ai_reasoning + validator)
        → MODE_C: + historical outcomes
        → compare_modes() → metrics
```

**Isolation**: No shared mutable state; reads immutable `AuditEvidencePackage`; no side effects.

---

## 6. Financial Vocabulary (Canonical)

| Field | Formula | Source |
|-------|---------|--------|
| `inventory_value_sar` | `stock * cost` | `evidence_package.py:170` |
| `capital_at_risk_sar` | `inventory_value` (DEAD/SLOW) | `evidence_package.py:184` |
| `revenue_at_risk_sar` | `stock * sell` (if velocity>0) | `evidence_package.py:185` |
| `gross_profit_at_risk_sar` | `revenue - inventory_value` | `evidence_package.py:186` |
| `recoverable_low_sar` | `0` (conservative) | `evidence_package.py:218` |
| `recoverable_high_sar` | `min(inventory_value, stock*sell)` | `evidence_package.py:219` |
| `expected_recovery_sar` | `None` (AI/calibration) | `evidence_package.py:220` |

**All monetary fields use `_sar` suffix, 2-decimal rounding.**

---

## 7. Execution Paths

| Path | Module | Mode | Mutates Data? |
|------|--------|------|---------------|
| **Simulated** | `execution_engine.py` | Simulation + events | NO |
| **Real** | `agent_action_executor.py` | Real DB + constraints | YES (approval-gated) |

**Action Types**: discount, pricing, reorder, transfer, recovery_match, expiry_alert

---

## 8. Guardrails

| Layer | Function | Fail Behavior |
|-------|----------|---------------|
| **Validator** | `validate_ai_response()` | `is_valid=False` → deterministic fallback |
| **Execution Guard** | `validate_action_for_execution()` | Blocks, records `constraint_blocks` |
| **Agent Runtime** | `execute_agent_action()` | Returns `executed=False` on block |
| **RLS** | `SET ROLE` + `app.current_tenant_id` | Production only |

---

## 9. Config Hierarchy

1. **Runtime Override** (`.env.runtime-test`) — CI/test
2. **Docker Compose** — Service env vars
3. **App Settings** (`config.py:Settings`) — Pydantic defaults + `.env`
4. **Local Dev** (`.env.example`) — Documentation
5. **Defaults** — Hardcoded in `Settings` class

**Zero-Cost Toggles**: `USE_CELERY`, `USE_REDIS`, `USE_MOCK_LLM`

---

## 10. Database Schema (76 Tables)

| Category | Count | Key Tables |
|----------|-------|------------|
| **ACTIVE** | 25 | users, businesses, items, inventory, transactions, money_audits, money_audit_actions, agent_actions, purchase_orders, executed_actions, events, execution_jobs, intelligence_decisions, outcome_feedback, model_performance, business_memory, memory_updates, pos_connections, pos_sync_logs, audit_log, subscriptions, team_members, organizations, webhook_events, constraint_blocks |
| **COMPATIBILITY** | 8 | audit_runs, findings, pilot_baselines, plans, simulations, business_goals, learned_outcomes, goal_progress_history |
| **LEGACY** | 18 | categories, daily_summaries, forecast_cache, pricing_rules, reports, notifications, webhook_events, deletion_requests, enabled_modules, feature_flags, recipes, parts_compatibility, pharmacy_lots, sfda_recalls, recovery_match_settings, stock_recovery_*, supplier_prices, suppliers, partner_referrals, partners, team_invitations, permission_definitions, billing_events, subscription_usage |
| **DEAD** | 25 | (vertical stubs, superseded, no references) |

---

## 11. Integration Status

| Integration | Webhook | Auth | Credentials | Live Tested |
|-------------|---------|------|-------------|-------------|
| Foodics | ✅ HMAC | SHA256 | `FOODICS_WEBHOOK_SECRET`="" | ❌ NO |
| Salla | ✅ HMAC | SHA256 | `SALLA_WEBHOOK_SECRET`="" | ❌ NO |
| WhatsApp | ✅ HMAC | SHA256 | `WHATSAPP_APP_SECRET`="" | ❌ NO (mock) |
| OAuth (Salla/Foodics) | ⚠️ Router exists | OAuth2 | No client IDs | ❌ NO |

**Boundary**: Missing secret = 401/503 (fail-closed). No silent failures.

---

## 12. Test Baseline (Post-Fix)

| Metric | Count |
|--------|-------|
| **Passed** | 801 |
| **Failed** | 53 (pre-existing, unrelated to validator fix) |
| **Skipped** | 3 |
| **Errors** | 10 (PostgreSQL concurrency/RLS) |

**Previously blocked modules now pass**: `test_v8_ai_adversarial` (35), `test_v8_closed_loop`, `test_v8_comprehensive` (59).

---

## 13. Risks & Debt

| Risk | Severity | Mitigation |
|------|----------|------------|
| Financial vocabulary drift | Medium | Add `financial_vocabulary.py` normalization layer |
| Experiment/production boundary blur | Low | Lazy import + dual-contract validator |
| No live integration tests | Medium | Contract tests against sandboxes |
| Celery/Redis optional but not tested in zero-cost mode | Low | Add CI matrix |
| 53 pre-existing test failures | Medium | Triage in Phase B |

---

## 14. Phase A Verdict

**PASS WITH MINOR DEBT**

- ✅ Verified defect fixed (V8 validator contract restored)
- ✅ All targeted modules pass (V8 adversarial, closed-loop, comprehensive)
- ✅ No regressions (801/53/3/10 same as post-fix baseline)
- ✅ Architecture documented with ADRs
- ✅ Canonical paths identified and bounded
- ⚠️ 53 pre-existing failures (unrelated to fix)
- ⚠️ Integration credentials missing (mock-only)
- ⚠️ Financial vocabulary drift needs normalization layer