# ADR: V8 Experiment vs Production Boundary

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

The V8/V11 experiment suite (`ab_decision_framework`, `ai_challenge`, `business_context`, `closed_loop_experiment`, `ai_reasoning`) is **strictly bounded** behind the `/ab-compare` endpoint with lazy imports. It does not participate in the canonical production decision path.

---

## 2. Boundary Evidence

### 2.1 Import Graph

```
PRODUCTION (canonical):
  routers/items.py → services/money_audit_service.py → decision_engine.py + nazm_planner.py
  routers/intelligence.py → services/intelligence_api.py → execution_engine.py
  routers/agent.py → services/agent_action_executor.py
  routers/money_audit.py → services/money_audit_service.py
  routers/webhook.py → services/pos_service.py

EXPERIMENT (lazy):
  routers/money_audit.py:666 → from app.services.ab_decision_framework import run_counterfactual_audit, compare_modes
    → services/ab_decision_framework.py
      → services/ai_reasoning.py (reason_about_item)
      → services/ai_response_validator.py (validate_ai_response, select_final_decision)
      → services/business_context.py (deterministic_decision_for_item)
      → services/ai_challenge.py (V11 challenge)
      → services/closed_loop_experiment.py
```

### 2.2 Production Entry Points

| Endpoint | Uses Experiment? | Notes |
|----------|------------------|-------|
| `POST /api/v1/money-audit` | **NO** | Direct `money_audit_service.run_money_audit` |
| `POST /api/v1/money-audit/ab-compare` | **YES** | Lazy import; `llm_caller=None` in production |
| `POST /api/v1/intelligence/execute` | **NO** | `execution_engine` (simulated) |
| `POST /api/v1/agent-actions/{id}/approve` | **NO** | `agent_action_executor` (real) |
| `GET /api/v1/decisions` | **NO** | `decision_engine` + `nazm_planner` |

### 2.3 Data Flow Isolation

```
PRODUCTION DATA FLOW:
  Upload → build_item_evidence → decision_engine → nazm_planner → action_registry → agent_action_executor

EXPERIMENT DATA FLOW (ab-compare):
  Upload → build_item_evidence → run_counterfactual_audit(llm_caller=None) → compare_modes
    → MODE_A: deterministic only (decision_engine)
    → MODE_B: deterministic + AI (ai_reasoning + validator) [NOT RUN IN PRODUCTION]
    → MODE_C: MODE_B + historical outcomes [NOT RUN IN PRODUCTION]
```

### 2.4 Key Isolation Properties

1. **No shared mutable state**: Experiment reads `AuditEvidencePackage` (immutable snapshot); writes only to in-memory results.
2. **No side effects**: `run_counterfactual_audit` never calls `agent_action_executor` or `execution_engine.execute_from_request`.
3. **Lazy import**: `ab_decision_framework` imported only inside `/ab-compare` handler (line 666 of `money_audit.py`).
4. **Test-only AI**: All test runs use `llm_caller=None`; real AI only if explicitly passed.
4. **Separate contracts**: `ai_response_validator` dual-contract ensures experiment uses object path; production uses string path.

---

## 3. Verification

### 3.1 Import Search
```
grep -r "ab_decision_framework" app/ --include="*.py" | grep -v test | grep -v __pycache__
# Only hit: app/services/money_audit.py:666 (inside /ab-compare handler)
```

### 3.2 Runtime Check
- Start backend → hit `/ab-compare` with `llm_caller=None` → returns MODE_A only (deterministic)
- No experiment code loaded on other endpoints

### 3.3 Test Coverage
- `test_v8_comprehensive.py`: Tests experiment logic in isolation (llm_caller=None)
- `test_v8_closed_loop.py`: Tests 60-day simulation (llm_caller=None)
- `test_phase12/13_closed_loop.py`: Tests experiment internals
- No integration test runs `/ab-compare` with real LLM

---

## 4. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Accidental `llm_caller` injection in production | Low | `ab-compare` handler doesn't accept LLM config; hardcoded None |
| Experiment code loaded at startup | None | Lazy import inside handler |
| Shared validator causing production bugs | None | Dual-contract dispatcher isolates paths |
| Experiment DB writes | None | Experiment uses in-memory `AuditEvidencePackage` only |

---

## 5. Conclusion

Boundary is **verified and enforced**. The experiment suite is a first-class testing/analysis tool, not a production code path. The `/ab-compare` endpoint provides a safe counterfactual evaluation surface without affecting live decisions.