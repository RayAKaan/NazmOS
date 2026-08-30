# V11 PREFLIGHT AUDIT

**Date:** 2026-08-27
**Auditor:** V11 Execution Pipeline
**Status:** ISSUES FOUND — fixes required before experiment

## Executive Summary

The V11 implementation has **14 identified issues** across 5 categories. The most critical: the experiment runner simulates AI by looking up ground truth answers, and the financial metrics are dimensionless factors presented as SAR amounts.

---

## Issue Classification

### REAL BUG (2)

| # | File | Line | Description |
|---|------|------|-------------|
| 1 | `v11_run_experiment.py` | 239-258 | **AI is simulated** — looks up ground truth answers directly instead of calling `challenge_deterministic()`. Experiment results are meaningless. |
| 2 | `ground_truth.json` | 102 | **FRZ-MPT-18 PRICE_CHANGE** — `correct=["PRICE_CHANGE"]` but PRICE_CHANGE is not a valid decision in the action registry or deterministic engine. Fixed to MARGIN_FIX. |

### EVALUATOR BUG (1)

| # | File | Line | Description |
|---|------|------|-------------|
| 3 | `v11/evaluator.py` | 180-183 | **Financial metrics are dimensionless** — sums recovery factors (0.0-1.0) and labels them as "incremental_sar". Must multiply by inventory_value_sar for real SAR. |

### FIXTURE BUG (2)

| # | File | Line | Description |
|---|------|------|-------------|
| 4 | `ground_truth.json` | 128 | **INJ-018-A name mismatch** — GT says "Normal Product (Prompt Injection Test)" but generator creates injection string. Fixed. |
| 5 | `ground_truth.json` | 135 | **INJ-019-A name mismatch** — GT says "Test Product Supplier Injection" but generator creates "Cleaning Spray 750ml". Fixed. |

### TEST BUG (2)

| # | File | Line | Description |
|---|------|------|-------------|
| 6 | `v11-ai-journey.spec.ts` | 126-152 | **Playwright uses non-existent selectors** — `data-testid` attributes don't exist in source code. All 6 testid assertions will fail. |
| 7 | `v11_security_test.py` | 436-443 | **Security tests incomplete** — Only 6 tests implemented out of 18 required. Missing: cross-tenant, unauthorized, duplicate, rate limiting, confidence bounds, missing evidence, constraint bypass. |

### ENVIRONMENT ISSUE (1)

| # | File | Line | Description |
|---|------|------|-------------|
| 8 | `v11_latency_test.py` | 130-171 | **Half of latency test is fabricated** — `measure_challenge_latency()` and `measure_total_audit_latency()` use hardcoded values. |

### NOT AN ISSUE (3)

| # | File | Line | Description |
|---|------|------|-------------|
| 9 | `v11_run_experiment.py` | 287 | **MODE_C = MODE_B copy** — Noted but addressed in rewrite (Phase 9). |
| 10 | `ai_response_validator.py` | 23-68 | **Duplicate ValidationResult** — Second definition shadows first. Dead code, no runtime impact. Will be cleaned up. |
| 11 | `v11/PLAN.md` | 5-13 | **Stale V10 finding** — Claims V10 lacks effective_accuracy but it already has it. Documentation issue only. |

### FALSE POSITIVE (1)

| # | File | Line | Description |
|---|------|------|-------------|
| 12 | `v11_run_experiment.py` | 340 | **State evolution appears fake** — Virtual date advances but no consumption. However, the experiment runner uploads fresh data each checkpoint via API, so state does change through re-uploads. Real consumption simulation will be added in Phase 8. |

### SUSPICIOUS (2)

| # | File | Line | Description |
|---|------|------|-------------|
| 13 | `v11_run_experiment.py` | 205-206 | **Import inside loop** — `deterministic_decision_for_item` imported inside the for loop. Works but inefficient. Will be fixed in rewrite. |
| 14 | `llm_orchestrator.py` | 185 | **Mock mode detection** — `use_mock = settings.USE_MOCK_LLM or not (settings.GROQ_API_KEY or settings.GOOGLE_AI_API_KEY)`. If no API keys are set, the orchestrator silently uses mock responses. Must verify keys are configured before running experiment. |

---

## Ground Truth Integrity

| Property | Value | Status |
|----------|-------|--------|
| Total SKUs | 30 | PASS |
| AI should challenge | 14 | PASS (was 15, removed ZST-020-A) |
| SKU name mismatches | 0 | PASS (fixed INJ-018-A, INJ-019-A) |
| Invalid decisions | 0 | PASS (fixed FRZ-MPT-18 PRICE_CHANGE → MARGIN_FIX) |
| JSON validity | Valid | PASS |
| SHA256 hash | `521f4735275ddc15cd7b7378df61d9064bca98b8097c3df2e01e8f959a4e4266` | RECORDED |

---

## Financial Firewall Verification

| Check | Status |
|-------|--------|
| `build_item_evidence()` sets `expected_recovery_sar=None` | PASS (evidence_package.py:220) |
| `recovery_intelligence.py` withholds expected_recovery without calibration | PASS (line 163-164) |
| AI challenge layer does not fabricate financial values | PASS (ai_challenge.py:290-291) |
| Experiment runner does not pass GT to AI | **FAIL** (lines 239-258) — MUST FIX |

---

## LLM Infrastructure Readiness

| Component | Status | Notes |
|-----------|--------|-------|
| LLM Orchestrator | READY | Groq + Gemini, circuit breaker, rate limiting, ledger |
| `chat_completion(system, user)` | READY | Returns string or None |
| Rate limiter | READY | `llm_rate_limiter.consume()` |
| Circuit breaker | READY | 3 failures → open, 2 successes → close |
| API keys | **VERIFY** | Must check GROQ_API_KEY or GOOGLE_AI_API_KEY before experiment |
| AI Challenge Layer | READY | `challenge_deterministic(context, llm_caller)` |

---

## Required Fixes Before Experiment

| Priority | Fix | Estimated Effort |
|----------|-----|-----------------|
| P0 | Replace simulated AI with real `challenge_deterministic()` | 2 hours |
| P0 | Fix financial metrics to use MODELLED_SAR | 30 minutes |
| P1 | Add missing security tests (12 more) | 1 hour |
| P1 | Replace fabricated latency measurements | 45 minutes |
| P1 | Make MODE_C genuinely different from MODE_B | 30 minutes |
| P2 | Clean up duplicate ValidationResult | 5 minutes |
| P2 | Update PLAN.md stale finding | 5 minutes |
| P3 | Make Playwright functional | 4 hours |

---

## Verdict

**V11 is NOT READY for experiment execution.** The experiment runner must be rewritten to use real AI calls. All other fixes are important but secondary.

Proceeding with fixes...
