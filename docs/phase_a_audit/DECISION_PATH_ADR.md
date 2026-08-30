# ADR: NazmOS Decision Path Canonicalization

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

The canonical production decision path is **`decision_engine.py` + `nazm_planner.py`**.  
The V8/V11 experiment framework (`ab_decision_framework`, `ai_challenge`, `business_context`, `closed_loop_experiment`, `ai_reasoning`) is **retained as an experiment harness** behind a lazy import in the `/ab-compare` money-audit endpoint. Both coexist.

---

## 2. Context

### 2.1 The Defect

`ai_response_validator.py` was rewritten to the Phase 3 §12 string-based contract:
```python
validate_ai_response(raw_output: str, known_evidence_ids, deterministic_decision, allowed_constraints)
```
Used by `opencode_brain.py:477` (production OpenCode brain path).

But the V8 experiment chain still required the **object-based V8 contract**:
```python
validate_ai_response(ai_result: AIReasoningResult, item, business, check_financial_claims=..., check_constraints=...)
```
plus missing symbols: `select_final_decision`, `_verify_financial_claims`, `ValidationResult.constraint_rejected`.

This caused a **poison-pill import chain**:
```
ab_decision_framework (ImportError) 
  → business_context (imports deterministic_decision_for_item) 
  → ai_challenge (imports StructuredContext) 
  → closed_loop_experiment
```

### 2.2 Resolution

`validate_ai_response` is now a **type dispatcher**:
- `str` first arg → §12 string contract (production, unchanged)
- `AIReasoningResult`-like object → V8 object contract (experiment)

Restored in `ai_response_validator.py`:
- `ValidationResult.constraint_rejected: bool = False`
- `_verify_financial_claims(ai_result, item) -> str | None`
- `select_final_decision(det, ai, conf, validation) -> (decision, source)`
- `_validate_ai_object_response` with constraint checks (blocked/strategic products, max discount %, MOQ vs budget)

Both contracts coexist in the same module. No tests modified.

---

## 3. Canonical Paths

| Layer | Canonical Module | Role |
|-------|------------------|------|
| **Decision Engine** | `decision_engine.py` | Core deterministic rules; single source of truth for classification → action mapping |
| **Planner** | `nazm_planner.py` | Orchestrates decision flow; used by API endpoints (`/decisions`, `/actions`) |
| **Experiment Harness** | `ab_decision_framework.py` + `ai_challenge.py` + `business_context.py` | Counterfactual A/B/C evaluation; V8/V11 AI challenge layer |
| **Experiment Entry** | `money_audit.py:666` (`/ab-compare` endpoint) | Lazy import; production surface for experiment |

### 3.1 Production Flow (Canonical)
```
Upload → Money Audit → Evidence Package → decision_engine.deterministic_decision_for_item()
    → nazm_planner.build_plan() → action_registry.execute()
```
No AI in the hot path. AI only via `opencode_brain` (async, best-effort, fail-closed).

### 3.2 Experiment Flow (V8/V11)
```
AuditEvidencePackage → run_counterfactual_audit(package, llm_caller, include_mode_c)
    → MODE_A: deterministic only
    → MODE_B: deterministic + AI reasoning (via ai_reasoning.reason_about_item)
    → MODE_C: MODE_B + historical outcomes
    → compare_modes() → metrics (ai_overrides, ai_agreements, ai_manual_reviews, ai_low_confidence, constraint_rejections)
```
Entry point: `POST /api/v1/money-audit/ab-compare` (lazy import, guarded by `llm_caller=None` in tests).

---

## 4. Artifact Map

| File | Status | Notes |
|------|--------|-------|
| `app/services/decision_engine.py` | **ACTIVE** | Canonical deterministic rules |
| `app/services/nazm_planner.py` | **ACTIVE** | Canonical plan builder |
| `app/services/opencode_brain.py` | **ACTIVE** | Production AI path (§12 string contract) |
| `app/services/ai_response_validator.py` | **ACTIVE** | Dual-contract dispatcher (both contracts) |
| `app/services/ab_decision_framework.py` | **COMPATIBILITY** | V8 experiment harness; not in production decision path |
| `app/services/ai_challenge.py` | **COMPATIBILITY** | V11 challenge layer; imported by ab_decision_framework |
| `app/services/business_context.py` | **COMPATIBILITY** | V11 context engine; module-level import of deterministic_decision_for_item |
| `app/services/closed_loop_experiment.py` | **TEST-ONLY** | 60-day simulation runner; not in production |
| `app/services/ai_reasoning.py` | **COMPATIBILITY** | AI reasoning + parsing; feeds experiment harness |
| `app/services/money_audit.py` | **ACTIVE** | Production audit; lazy imports experiment at `/ab-compare` |

---

## 5. Consequences

### Positive
- V8/V11 experiment suite unblocked (35+59 tests now passing)
- Production §12 contract untouched; OpenCode brain path unchanged
- `/ab-compare` endpoint functional for counterfactual evaluation
- Clear architectural boundary: deterministic = production; AI = experiment/augmentation

### Negative
- Two decision-path codebases to maintain (mitigated: experiment clearly labeled)
- `business_context.py` module-level import creates minor coupling (accepted)

---

## 6. Verification

- `test_v8_ai_adversarial.py`: 35 passed (was collection-blocked)
- `test_v8_closed_loop.py`: passed (was collection-blocked)
- `test_v8_comprehensive.py`: 59 passed
- `test_phase1_decision_safety_comprehensive.py`: 18 pre-existing failures unchanged
- `tests/phase4/test_opencode_brain.py`: 2 passed (production §12 path)
- Full suite: 801 passed / 53 failed / 3 skipped / 10 errors (baseline 746/73/3/10)

No regressions introduced.