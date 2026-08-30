# NAZMOS V9 AI Value Reality Test Report

**Date:** 2026-08-26  
**Author:** NAZMOS Automated Experiment Pipeline  
**Classification:** Honest — no softening, no spin  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Question Answered](#2-question-answered)
3. [Honest Verdict](#3-honest-verdict)
4. [Experiment Design](#4-experiment-design)
5. [What Was Tested](#5-what-was-tested)
6. [How It Was Tested](#6-how-it-was-tested)
7. [Three Decision Modes](#7-three-decision-modes)
8. [Five Adversarial Businesses](#8-five-adversarial-businesses)
9. [Six Virtual Checkpoints](#9-six-virtual-checkpoints)
10. [Ground Truth (Committed Before Run)](#10-ground-truth)
11. [Constraint Enforcement](#11-constraint-enforcement)
12. [AI Infrastructure](#12-ai-infrastructure)
13. [AI Call Ledger Results](#13-ai-call-ledger-results)
14. [Decision Accuracy Comparison](#14-decision-accuracy-comparison)
15. [Override Analysis (B vs A)](#15-override-analysis)
16. [Adoption Source Analysis](#16-adoption-source-analysis)
17. [Per-Business Breakdown](#17-per-business-breakdown)
18. [Longitudinal Trend](#18-longitudinal-trend)
19. [Financial Impact (Simulated Outcomes)](#19-financial-impact)
20. [Persistence Proof](#20-persistence-proof)
21. [Backend Regression](#21-backend-regression)
22. [Playwright E2E Regression](#22-playwright-e2e-regression)
23. [Defects Found During V9](#23-defects-found)
24. [Rate Limiting Experience](#24-rate-limiting)
25. [Infrastructure Bottleneck Analysis](#25-infrastructure-bottleneck)
26. [What AI Actually Did When It Worked](#26-what-ai-actually-did)
27. [What Would Change the Result](#27-what-would-change)
28. [Cost Accounting](#28-cost-accounting)
29. [Limitations](#29-limitations)
30. [Recommendation](#30-recommendation)
31. [Appendix: Methodology](#31-appendix-methodology)

---

## 1. Executive Summary

V9 executed 30 checkpoints (6 virtual time-windows × 5 adversarial businesses) against a live NAZMOS stack with real Groq `openai/gpt-oss-120b` and Google Gemini APIs. The experiment ran MODE_A (deterministic only), MODE_B (+AI reasoning), and MODE_C (+AI+historical outcomes) against identical business states.

**The experiment failed to produce a meaningful answer about AI value.** Only 8 of 984 AI calls (0.8%) succeeded due to provider rate limits and circuit breaker exhaustion. The AI was effectively offline for 99.2% of the experiment. Both MODE_B and MODE_C decisions were almost entirely deterministic fallbacks.

Where AI did produce decisions (8 successful calls across the entire run), it generated **0 GOOD overrides and 1 BAD override** across 186 total overrides. The net incremental value of AI reasoning is **-1** (one BAD override, zero GOOD ones).

The deterministic engine alone (MODE_A) achieved 44.83% correct decision rate across all evaluated SKUs. MODE_B achieved 45.40%. MODE_C achieved 45.45%. The differences are within noise and are **not attributable to AI** since the AI was offline.

---

## 2. Question Answered

**Q: Does adding AI reasoning to NazmOS produce better business decisions and financial outcomes than the deterministic engine alone?**

**A: Cannot determine.** The experiment infrastructure could not reliably invoke AI at the required scale (984 calls, 0.8% success rate). The data is real. The Groq calls are real. But the sample size of successful AI interventions (8 calls) is too small for any statistical conclusion. The honest answer is NOT YET — we cannot say yes or no.

---

## 3. Honest Verdict

| Dimension | Grade | Rationale |
|-----------|-------|-----------|
| Did the experiment execute? | **A** | 30/30 checkpoints, 5/5 businesses, real stack, real Groq |
| Did AI actually reason? | **D** | 0.8% success rate; 99.2% fell back to deterministic |
| Did AI improve decisions? | **D** | 0 GOOD overrides, 1 BAD override out of 186 |
| Did AI improve financial outcomes? | **D** | Cannot attribute — AI was offline |
| Is the deterministic engine sufficient? | **B** | 44.83% correct is honest; room for improvement exists |
| Infrastructure readiness for AI? | **D** | Rate limits, circuit breaker, provider caps make scaled AI unreliable |

**Final classification: NOT YET.** The question remains open because the AI was not available at sufficient scale to answer it.

---

## 4. Experiment Design

- **5 adversarial businesses** with 7-10 SKUs each, embedded cases A-J (prompt injection, evidence holes, zero-stock, price collapse, ghost PO)
- **6 virtual checkpoints** (d00, d07, d14, d30, d45, d60) simulating business evolution
- **3 modes** compared on identical business state: A (deterministic), B (+AI), C (+AI+outcomes)
- **Owner adoption policy**: C > B > A (best available recommendation per SKU)
- **Simulated outcomes** with pre-committed recovery factors: correct=0.85×, bad=0.25×, manual=0×
- **Ground truth** committed to `scripts/v9/ground_truth.json` BEFORE data generation
- **Outcome model** committed to `scripts/v9/outcome_model.json` BEFORE data generation
- **AI call ledger** at `backend/tmp/v9_ai_calls.jsonl` (every call logged with provider/outcome/latency/tokens)

---

## 5. What Was Tested

| Component | Status |
|-----------|--------|
| Deterministic financial engine | Real — same engine as V1/V2 |
| AI reasoning (Groq gpt-oss-120b) | Real — 181 calls attempted, 8 succeeded |
| AI reasoning (Google Gemini) | Real — 173 calls attempted, 0 succeeded |
| AI call ledger | Real — 984 JSONL entries |
| Constraint enforcement | Real — 10 constraint types |
| A/B/C comparison framework | Real — per-SKU parallel comparison |
| Owner adoption (C>B>A) | Real — per-SKU selection |
| Simulated outcomes | Real — recovery factors applied |
| DB persistence | Real — PostgreSQL mutations verified |
| Playwright E2E | Real — 19/19 passing |

---

## 6. How It Was Tested

For each checkpoint × business:
1. Upload sales window CSV (+ inventory at d00)
2. Wait for Celery ingest to complete
3. POST `/api/v1/money-audit/generate` to create audit session
4. POST `/api/v1/money-audit/{id}/ab-compare` with `max_ai_calls=6`
   - MODE_A: deterministic only (no AI calls)
   - MODE_B: +AI reasoning per SKU
   - MODE_C: +AI reasoning + historical outcome context
5. Evaluate all three modes against ground truth
6. Classify overrides B vs A (GOOD/BAD/NEUTRAL/UNRESOLVED)
7. Owner adopts C>B>A per SKU
8. Approve/execute/reject according to adoption
9. Complete with SIMULATED outcome
10. Persist to PostgreSQL

Between checkpoints: baseline consumption applied via psql (SIMULATED_CONSUMPTION label).

---

## 7. Three Decision Modes

| Mode | Inputs | AI Calls | Description |
|------|--------|----------|-------------|
| A | Financial data + constraints | 0 | Pure deterministic engine |
| B | A + LLM reasoning | up to 6 per SKU | AI reasons about each decision |
| C | B + historical outcomes | up to 6 per SKU | AI also sees past outcome data |

---

## 8. Five Adversarial Businesses

| Business | Type | SKUs | Cases | Special Challenges |
|----------|------|------|-------|-------------------|
| B1 Healthy Supermarket | Supermarket | 8 | A,C,F | Prompt injection (INJ-SAR-02, INJ-DAT-03), zero-stock (BBQ-GLL-05) |
| B2 Poor Baqala | Baqala | 8 | A,D,E | Cash constraint, price collapse, ghost PO, evidence holes |
| B3 Growing Supermarket | Grocery | 8 | B,G,I | Inbound PO, seasonal patterns, volume anomaly |
| B4 Seasonal Retailer | Retail | 7 | D,F,J | Extreme seasonality, fast-moving inventory |
| B5 Cash-Constrained Restaurant | Restaurant | 7 | A,E,H | Minimum margin constraints, blocked transfers |

---

## 9. Six Virtual Checkpoints

| Checkpoint | Gap | Cumulative Days | Purpose |
|------------|-----|-----------------|---------|
| d00 | 0 | 0 | Baseline — full inventory + initial sales |
| d07 | 7d | 7 | Early signals — first trends emerge |
| d14 | 7d | 14 | Two-week patterns — demand crystallizing |
| d30 | 16d | 30 | Monthly view — seasonal patterns visible |
| d45 | 15d | 45 | Mid-quarter — decisions become critical |
| d60 | 15d | 60 | End-of-quarter — final assessment |

---

## 10. Ground Truth

Committed to `scripts/v9/ground_truth.json` BEFORE data generation. Contains:
- Per-SKU correct/bad decisions per business
- Constraint expectations per business
- 10 constraint types with expected values
- Evaluation logic in `scripts/v9/evaluator.py`

Engines NEVER read ground truth. Evaluation happens AFTER decisions are made.

---

## 11. Constraint Enforcement

10 constraint types enforced via `constraint_service.py`:

| Constraint | B1 | B2 | B3 | B4 | B5 |
|------------|----|----|----|----|-----|
| cash_budget_sar | 50000 | 8000 | 35000 | 15000 | 12000 |
| minimum_margin_pct | 15% | 8% | 20% | 25% | 30% |
| max_discount_pct | 20% | 10% | 15% | 30% | 5% |
| blocked_discount_products | INJ-* | — | — | — | — |
| strategic_products | — | — | GRW-OIL-03 | — | — |
| minimum_safety_stock | 10 | 5 | 15 | 8 | 5 |
| maximum_purchase_amount | 20000 | 5000 | 15000 | 10000 | 8000 |
| blocked_transfer_routes | — | — | — | OUT-* | — |

---

## 12. AI Infrastructure

| Component | Configuration |
|-----------|--------------|
| Primary LLM | Groq `openai/gpt-oss-120b` |
| Secondary LLM | Google Gemini (Flash) |
| Fallback | Deterministic (mock) |
| Circuit breaker | 3 failures → open for 60s |
| Per-request budget | max_ai_calls=6 (configurable) |
| AI call delay | 2.0s between calls |
| Ledger | JSONL at `/app/tmp/v9_ai_calls.jsonl` |

---

## 13. AI Call Ledger Results

| Metric | Value |
|--------|-------|
| Total AI calls attempted | 984 |
| Successful (ok) | **8 (0.8%)** |
| Rate limited | 346 (35.2%) |
| All providers failed | 173 (17.6%) |
| Circuit open | 457 (46.4%) |
| By provider: Groq | 181 calls |
| By provider: Google | 173 calls |
| By provider: None/mock | 630 calls |
| Total tokens consumed | 11,129 |
| Average latency | 80ms |

**This is the critical finding: 99.2% of AI calls failed.** The AI was effectively offline for the entire experiment.

---

## 14. Decision Accuracy Comparison

### Mandated Table 1: Mode Comparison

| Mode | Correct | Bad Action | Unnecessary | Manual | Neutral | Total Evaluated | Correct Rate | Bad Rate |
|------|---------|------------|-------------|--------|---------|----------------|-------------|----------|
| A (deterministic) | 78 | 18 | 34 | 27 | 17 | 174 | **44.83%** | 10.34% |
| B (+AI reasoning) | 79 | 19 | 33 | 25 | 18 | 174 | **45.40%** | 10.92% |
| C (+AI+outcomes) | 85 | 23 | 31 | 26 | 22 | 187 | **45.45%** | 12.30% |

**INCREMENTAL AI VALUE:**
- B vs A: +0.57 percentage points (NOT statistically significant; AI was offline)
- C vs A: +0.62 percentage points (NOT statistically significant; AI was offline)

### Note on "correct rate"

The 44.83% rate includes ALL evaluated decisions (correct, bad, unnecessary, manual, neutral). Many SKUs where DO_NOTHING was correct had engines recommending action, counted as "unnecessary_action." Per-business rates are more informative (see Section 17).

---

## 15. Override Analysis

### Mandated Table 2: Override Classification (B vs A)

| Classification | Count | Description |
|---------------|-------|-------------|
| GOOD_OVERRIDE | **0** | AI corrected a deterministic bad action |
| BAD_OVERRIDE | **1** | AI introduced a bad action where deterministic was correct |
| NEUTRAL_OVERRIDE | **185** | AI and deterministic agreed (no actual override) |
| UNRESOLVED | **0** | Cannot determine who was right |
| **Total** | **186** | |
| **Net value** | **-1** | One BAD override, zero GOOD ones |

**The single BAD override**: B1 d00 SKU BBQ-CHR-04 — deterministic said MANUAL_REVIEW, AI said DISCOUNT. Ground truth classified this as a bad action (the product was in the injection list). AI was wrong; deterministic was right.

---

## 16. Adoption Source Analysis

| Source | Count | Percentage |
|--------|-------|-----------|
| C (AI+outcomes) | 177 | 94.7% |
| B (AI reasoning) | 9 | 4.8% |
| A (deterministic only) | 0 | 0% |

Adoption was overwhelmingly from Mode C because C>B>A policy selects the "best available" recommendation per SKU. Since C and B almost always agreed with A (185/186 overrides were NEUTRAL), the source label is misleading — most C-source decisions were actually deterministic in content.

---

## 17. Per-Business Breakdown

| Business | A Correct% | B Correct% | C Correct% | Key Observation |
|----------|-----------|-----------|-----------|-----------------|
| B1 Healthy Supermarket | **100%** | 91% | **100%** | AI hurt B1 (1 BAD override) |
| B2 Poor Baqala | 81% | 81% | 80% | Modes essentially identical |
| B3 Growing Supermarket | **100%** | **100%** | **100%** | All modes perfect |
| B4 Seasonal Retailer | 62% | 62% | 62% | All modes identical — hard business |
| B5 Cash-Constrained Restaurant | 76% | 76% | 70% | C hurt B5 (3 extra bad actions) |

**Key insight:** Where AI had any effect at all (8 successful calls), it made things worse in 2 businesses and better in 0.

---

## 18. Longitudinal Trend

| Checkpoint | A Avg | B Avg | C Avg |
|------------|-------|-------|-------|
| d00 | 50.00% | 50.00% | 49.52% |
| d07 | 64.43% | 64.43% | 66.95% |
| d14 | 51.33% | 51.33% | 54.76% |
| d30 | 32.09% | 32.09% | 30.95% |
| d45 | 36.43% | 36.43% | 37.81% |
| d60 | 37.90% | 40.76% | 35.24% |

**Observation:** Decision quality degrades over time as inventory positions become more complex. At d00 (baseline), accuracy is highest. By d30-d60, the cumulative effects of consumption, seasonality, and constraint tightening make decisions harder for ALL modes.

The one checkpoint where AI showed positive signal was d60_B2: Mode B achieved 57.14% vs Mode A's 42.86%. But this single data point (with only 1-2 successful AI calls) is not statistically meaningful.

---

## 19. Financial Impact (Simulated Outcomes)

All outcomes were SIMULATED (labeled `v9_SIMULATED_OUTCOME`). Recovery factors applied:
- Correct action: 0.85× expected recovery ± 5% noise
- Bad action: 0.25× expected recovery ± 5% noise
- Manual review: 0× (no action taken)
- Acceptable manual: 0× (no action taken)

Financial attribution is meaningless because the AI was offline. Any observed differences between modes are noise from the deterministic engine, not AI value.

---

## 20. Persistence Proof

| Verification | Status |
|-------------|--------|
| Checkpoint JSONs written to disk | **30/30** |
| Businesses created in PostgreSQL | **5/5** (separate owners) |
| Uploads processed | 37 total |
| Audit sessions created | 31 total |
| Audit actions generated | 272 total |
| Outcomes recorded | 63 total |
| AI call ledger entries | 984 JSONL lines |
| Backend restart survival | Verified (V2 proof) |

---

## 21. Backend Regression

| Test Suite | Status | Count |
|-----------|--------|-------|
| Comprehensive tests | ✅ PASS | 59 |
| Adversarial tests | ✅ PASS | 15 |
| Business Decision Loop tests | ✅ PASS | 34 |
| **Total backend** | **✅ ALL PASS** | **108** |

---

## 22. Playwright E2E Regression

| Suite | Status | Count | Duration |
|-------|--------|-------|----------|
| Auth setup | ✅ PASS | 1 | 2.1s |
| Navigation | ✅ PASS | 5 | 4.8s |
| Dashboard | ✅ PASS | 3 | 5.2s |
| Upload | ✅ PASS | 2 | 3.1s |
| Money Audit | ✅ PASS | 4 | 8.7s |
| Owner Journey | ✅ PASS | 2 | 6.4s |
| Business Decision Loop | ✅ PASS | 2 | 13.1s |
| **Total E2E** | **✅ ALL PASS** | **19/19** | **43.4s** |

---

## 23. Defects Found During V9

| # | Severity | Description | Status |
|---|----------|-------------|--------|
| 1 | P0 | Auth resume: `RUN_TS` recomputed, owner emails mismatched businesses | Fixed |
| 2 | P0 | Bootstrap is first-store-only: 5 businesses need 5 owners | Fixed |
| 3 | P0 | Master file not saved after bootstrap: resume can't find owners | Fixed |
| 4 | P1 | Auth register hits rate limit on resume; login_only mode needed | Fixed |
| 5 | P1 | Stale Authorization header interferes with login | Fixed |
| 6 | P1 | Master overwritten with empty businesses on resume | Fixed |
| 7 | P1 | PowerShell `ConvertTo-Json` mangled master JSON | Fixed (Python) |

---

## 24. Rate Limiting Experience

| Endpoint | Limit | Observed Impact |
|----------|-------|----------------|
| Auth register | 10/5min | Hit during resume debugging (6 attempts in 3min) |
| Auth login | 30/5min | Hit on first resume attempt (247s Retry-After) |
| Upload | 10/5min | No impact (enterprise plan) |
| Groq API | ~30 RPM | **CRITICAL**: 346 rate-limited calls out of 984 |
| Gemini API | ~20 req/day | **CRITICAL**: 173 all-providers-failed (quota exhausted) |

---

## 25. Infrastructure Bottleneck Analysis

**Why did 99.2% of AI calls fail?**

1. **Groq RPM cap (~30 requests/minute)**: Each `/ab-compare` with 6 AI calls per mode (B+C=12 calls) × ~8 SKUs = ~96 calls per business checkpoint. At 30 RPM, this requires ~3.2 minutes per checkpoint JUST for Groq calls. With 5 businesses × 6 checkpoints = 30 runs, the total Groq requirement was ~2,880 calls. Groq's RPM limit made this impossible.

2. **Gemini daily quota (~20 requests/day)**: Exhausted early in V2 debugging. Could not serve any V9 calls.

3. **Circuit breaker**: After 3 consecutive failures, the circuit opened for 60 seconds. With 99.2% failure rate, the circuit was open for most of the experiment (457 circuit_open outcomes).

4. **Combined effect**: The AI was effectively a no-op. Mode B and Mode C decisions were deterministic fallbacks for 99.2% of SKUs.

---

## 26. What AI Actually Did When It Worked

Only 8 calls succeeded. From the ledger and checkpoint data:

- **d00 B1**: AI recommended DISCOUNT for BBQ-CHR-04 (ground truth: bad action). Deterministic had MANUAL_REVIEW (neutral/better). **AI was WRONG.**
- **d07 B3**: AI agreed with deterministic on 1 SKU (NEUTRAL). No value.
- **d14 B3**: AI agreed with deterministic on 1 SKU (NEUTRAL). No value.
- **d45 B5**: AI agreed with deterministic on 1 SKU (NEUTRAL). No value.
- **d60 B2**: AI recommended DO_NOTHING for SLW-CAN-04 (deterministic: MANUAL_REVIEW). Both are acceptable. **NEUTRAL.**
- **d60 B2**: AI agreed with deterministic on 1 SKU. No value.

**Summary of successful AI behavior**: 1 BAD override, 0 GOOD overrides, ~5 NEUTRAL agreements. The AI had no positive impact.

---

## 27. What Would Change the Result

1. **Dedicated AI infrastructure**: Paid Groq Enterprise (higher RPM), dedicated Gemini instance, or self-hosted LLM (Llama, Mistral) to eliminate rate limiting.
2. **Reduced AI call volume**: Instead of 6 calls per SKU, use 1-2 calls with better prompts.
3. **Smarter circuit breaker**: Progressive backoff instead of binary open/close.
4. **Batch AI processing**: Process all SKUs in a single prompt instead of per-SKU calls.
5. **Larger sample**: More businesses, more checkpoints, longer timeline.

---

## 28. Cost Accounting

| Item | Quantity | Cost |
|------|----------|------|
| Groq API calls (984) | 11,129 tokens | ~$0.00 (free tier) |
| Gemini API calls | 173 (all failed) | $0.00 (exhausted quota) |
| PostgreSQL compute | 30 checkpoints × 5 businesses | Included in local stack |
| Playwright tests | 19/19 | $0.00 (local) |
| **Total external cost** | | **~$0.00** |

The experiment cost zero dollars in API fees because Groq and Gemini free tiers absorbed all calls. This is both a strength (reproducible) and a weakness (free tiers are rate-limited, which is what broke the experiment).

---

## 29. Limitations

1. **AI was offline 99.2%** — the experiment cannot answer the AI value question.
2. **Simulated outcomes** — real business outcomes would require human validation.
3. **Ground truth is artificial** — adversarial cases are designed to stress-test, not replicate real-world distributions.
4. **5 businesses is small** — no statistical significance.
5. **60-day window is short** — seasonal patterns may require 6-12 months.
6. **Single stack deployment** — no multi-region redundancy tested.
7. **No A/B randomization** — all three modes run against identical state, not randomized assignment.

---

## 30. Recommendation

**DO NOT PROCEED with AI integration for decision-making at this time.**

**DO PROCEED with:**
1. Dedicated LLM infrastructure (Groq Enterprise or self-hosted) before any AI integration
2. Optimized prompt engineering (batch SKUs, reduce call volume by 10×)
3. Deterministic engine improvements (the 44.83% correct rate has room for improvement via better heuristics, not AI)
4. Real-world pilot with 1-2 Saudi retail partners over 6 months
5. Re-run V9 experiment with dedicated infrastructure

**The honest answer: we built the right experiment, got real data, but the AI infrastructure was not ready for the experiment we designed. The deterministic engine is the reliable foundation. AI remains a future layer that needs proper infrastructure first.**

---

## 31. Appendix: Methodology

### Evaluator Logic
- `classify_decision(biz_key, sku, decision)` → correct | bad_action | unnecessary_action | acceptable_manual | neutral | unknown_sku
- `classify_override(biz_key, sku, det, ai_final)` → GOOD_OVERRIDE | BAD_OVERRIDE | NEUTRAL_OVERRIDE | UNRESOLVED
- `score_mode_results(biz_key, mode_results)` → per-sku verdicts + aggregate rates
- `recovery_factor_for(verdict)` → 0.85 (correct) | 0.25 (bad) | 0.0 (manual)
- `consumption_rate(biz_key, sku)` → daily units from outcome_model.json

### Scripts
| Script | Purpose |
|--------|---------|
| `scripts/v9_generate_business_data.py` | Generate 5 businesses × 6 checkpoint CSVs |
| `scripts/v9_run_experiment.py` | Execute full longitudinal experiment |
| `scripts/v9_metrics.py` | Aggregate checkpoint results into metrics |
| `scripts/v9_summary.py` | Quick checkpoint-level summary |
| `scripts/v9_inspect.py` | Detail inspection of individual checkpoints |
| `scripts/v9/evaluator.py` | Decision evaluation against ground truth |
| `scripts/v9/ground_truth.json` | Ground truth (committed before run) |
| `scripts/v9/outcome_model.json` | Recovery factors + consumption rates |

### Data
| Path | Content |
|------|---------|
| `sample_data/v9/` | 36 CSV files (5 businesses × [inventory + 6 sales windows]) |
| `results/v9/checkpoint_*.json` | 30 checkpoint result files |
| `results/v9/v9_experiment_master.json` | Experiment metadata |
| `backend/tmp/v9_ai_calls.jsonl` | AI call ledger (984 entries) |

### Environment
- **Stack**: Docker Compose local (PG17, Redis7, Celery×2, FastAPI, Next.js)
- **OS**: Windows (PowerShell)
- **Python**: 3.14
- **LLM**: Groq `openai/gpt-oss-120b` primary, Google Gemini secondary
- **Duration**: ~1.5 hours total (setup + 30 checkpoints + resume)
