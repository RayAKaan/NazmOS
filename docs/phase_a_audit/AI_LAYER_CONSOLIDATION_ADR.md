# ADR: AI Layer Consolidation — Validator/Guardrail Contract Canonicalization

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

The AI layer has **three distinct contracts** serving different purposes. Canonicalization means documenting boundaries, not merging.

| Contract | Module | Purpose | Caller |
|----------|--------|---------|--------|
| **§12 String Contract** | `ai_response_validator._validate_string_response` | Validate raw OpenCode JSON output | `opencode_brain.py` (production) |
| **V8 Object Contract** | `ai_response_validator._validate_ai_object_response` | Validate structured `AIReasoningResult` against evidence | `ab_decision_framework` (experiment) |
| **V11 Challenge Contract** | `ai_challenge` + `select_final_decision_v11` | Challenge deterministic decisions with evidence | `ab_decision_framework` (V11 mode) |

---

## 2. Current State

### 2.1 `ai_response_validator.py` (574 lines) — **DUAL CONTRACT** ✅ FIXED
- Dispatcher on first-arg type (str vs object)
- §12 path: JSON schema, enum, confidence, evidence IDs, financial hallucination, injection
- V8 path: object fields, evidence validation, financial claims, constraint rejection
- Shared: `ValidationResult` with `constraint_rejected`, `financial_hallucination_detected`, `injection_detected`

### 2.2 `ai_reasoning.py` (352 lines) — **REASONING ENGINE**
- `reason_about_item(item, business, llm_caller, include_historical)` → `AIReasoningResult`
- `_parse_ai_response(raw_json)` → `AIReasoningResult` (used by `opencode_brain` as fallback)
- `AIReasoningResult`: decision, confidence, reasoning, evidence_ids, risk_flags, recommended_action

### 2.3 `ai_challenge.py` (400 lines) — **V11 CHALLENGE LAYER**
- `challenge_deterministic(context)` → `AIChallengeResponse`
- `select_final_decision_v11(det, challenge, context)` → (decision, source)
- Sources: `DETERMINISTIC_CONFIRMED`, `DETERMINISTIC_NO_CHALLENGE`, `CHALLENGE_INVALID`, `CHALLENGE_CONSTRAINT_REJECTED`, `AI_CHALLENGE_ACCEPTED`
- Uses `StructuredContext` from `business_context.py`

### 2.4 `opencode_brain.py` (547 lines) — **PRODUCTION AI PATH**
- Calls OpenCode CLI, parses stdout JSON
- Validates via `ai_response_validator` (§12 string contract)
- Fallback: deterministic decision on validation failure
- **No direct dependency on experiment modules**

### 2.5 `llm_orchestrator.py` (660 lines) — **MULTI-LLM ROUTING**
- Routes to OpenCode, Anthropic, OpenAI
- Rate limiting via `llm_rate_limiter`
- Used by: `opencode_brain`, `runtime`, potentially `ai_reasoning`

### 2.6 `ab_decision_framework.py` (708 lines) — **EXPERIMENT HARNESS**
- `run_counterfactual_audit(package, llm_caller, include_mode_c)`
- Three modes: A (deterministic), B (+AI), C (+history)
- `compare_modes()` → metrics (ai_overrides, ai_agreements, ai_manual_reviews, ai_low_confidence, constraint_rejections)

---

## 3. Contract Canonicalization

### 3.1 `ai_response_validator` — **CANONICAL GUARDRAIL**
Both contracts in one module, dispatched by type. **Do not split** — single source of truth for validation logic.

### 3.2 `ai_reasoning` — **EXPERIMENT REASONING**
Only used by `ab_decision_framework`. Production uses `opencode_brain` → validator directly.

### 3.3 `ai_challenge` — **V11 EXPERIMENT**
Only used by `ab_decision_framework` V11 mode. Not in production path.

### 3.4 `opencode_brain` — **PRODUCTION AI**
Uses §12 string contract only. No experiment dependencies.

### 3.5 `llm_orchestrator` / `llm_rate_limiter` — **SHARED INFRASTRUCTURE**
Used by both production (`opencode_brain`) and experiment (`ai_reasoning`).

---

## 4. Guardrail Surface

| Layer | Function | Fail-Closed Behavior |
|-------|----------|----------------------|
| **Validator** | `validate_ai_response` | Returns `ValidationResult(is_valid=False)` → fallback to deterministic |
| **Opencode Brain** | `_deterministic_fallback()` | Always returns valid decision |
| **Execution Guard** | `validate_action_for_execution()` | Blocks action, records `constraint_blocks` |
| **Agent Runtime** | `execute_agent_action()` | Returns `executed=False` on constraint block |

---

## 5. No-Merge Rationale

| Module | Keep Separate? | Reason |
|--------|----------------|--------|
| `ai_response_validator` | ✅ Single module, dual contract | Both paths need same validation logic |
| `ai_reasoning` | ✅ Experiment only | Production uses OpenCode CLI, not structured reasoning |
| `ai_challenge` | ✅ V11 experiment | Different paradigm (challenge vs free-form reasoning) |
| `opencode_brain` | ✅ Production | Direct OpenCode integration, no experiment deps |
| `llm_orchestrator` | ✅ Shared infra | Rate limiting, provider routing for all LLM callers |

---

## 6. Verification

- `opencode_brain` imports only `ai_response_validator` (no experiment deps) ✅
- `ab_decision_framework` imports `ai_reasoning`, `ai_challenge`, `business_context` ✅
- Lazy import in `money_audit.py:666` isolates experiment ✅
- Tests: `test_v8_*` exercise experiment; `test_opencode_brain.py` exercises production ✅

---

## 7. Future Work (Post Phase A)

1. Extract `financial_hallucination` patterns to shared constants
2. Unify `select_final_decision` (V8) and `select_final_decision_v11` (V11) semantics
3. Add `ai_budget` enforcement to `llm_orchestrator`
4. Document `llm_rate_limiter` as canonical rate limiter