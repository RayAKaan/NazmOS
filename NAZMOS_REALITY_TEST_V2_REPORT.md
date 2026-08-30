# NAZMOS REALITY TEST — BUSINESS DECISION LOOP V2 REPORT

**Generated**: 2026-08-26
**Environment**: Docker Compose local stack — PostgreSQL 17, Redis 7, Celery worker+beat, FastAPI (Python 3.12), Next.js 16
**LLM**: Google Gemini via real HTTP API (`USE_MOCK_LLM=false`)
**Verdict format**: every claim below is backed by an executed runtime check. Where something could NOT be demonstrated, it says so.

---

## 1. Executive Verdict

The Business Decision Loop is now **runtime-proven through the full execution chain on a real stack**: upload → Celery ingestion → PostgreSQL → money audit → approval → **execution that mutates business state in the database** → outcome recording with prediction error → **survival across a backend restart** → read-back through the evidence API. Browser-level E2E passes 19/19.

What is **not yet proven**: whether NazmOS's AI reasoning produces *better* decisions than deterministic alone at full scale. The MODE_A vs MODE_B experiment ran with real Gemini and produced genuine overrides where quota allowed, but the project's free tier (~20 requests/day/model) was exhausted mid-experiment by debugging iterations. This is a **quota limitation, not an architecture failure** — and the degradation path it triggered behaved exactly as designed (circuit breaker → deterministic fallback, zero crashes).

---

## 2. Runtime Checks Executed and Their Results

### Step 3 — Persistence Proof (`scripts/v2_step3_persistence_proof.py`) — **11/11 PASSED**

| # | Check | Method | Result |
|---|-------|--------|--------|
| P1 | Celery async ingestion completes | API + worker logs | PASS — 147 sales rows + 30 inventory rows ingested |
| P2a | Approve endpoint | API | PASS |
| P2b | **Execution mutates business state** | `psql` ground truth inside Postgres container | PASS — `inventory.current_stock` 0.0 → 10.0 |
| P2c | Execution writes audit trail | `psql` on `executed_actions` | PASS |
| P3a/b | Completion persists to `outcome_feedback` | `psql` | PASS |
| P3c | **Prediction error computed & stored** | JSON delta field | PASS — `prediction_error_pct = 5.54` |
| P4a | Backend container restarts healthy | docker restart + readiness poll | PASS |
| P4b | **Outcome survives restart** | row count before/after restart | PASS — persistence is real, not session-scoped |
| P5 | Evidence endpoint reads persisted outcomes from PG | API | PASS |

### Step 4 — 5-Business Reality Run (`scripts/v2_step4_reality_run.py`)

| Business | Type | Actions generated | Executed (state mutated) | Prediction error % recorded |
|----------|------|------------------|-------------------------|------------------------------|
| Al-Olaya Baqala | baqala | 12 | 2 | 4.03 |
| Corniche Supermarket | supermart | 12 | 2 | 4.03 |
| Dhahran Cafe | cafe | 12 | 2 | 4.03 |
| Taif Restaurant | restaurant | 12 | 2 | 4.03 |
| Khobar General Retail | retail | 12 | 2 | 4.03 |
| **Total** | | **60** | **10/10 approved→executed→completed** | all persisted to `outcome_feedback` |

Every executed action followed the chain: prediction → constraint check → owner approval (API) → execution → **verified PostgreSQL mutation** → reported actual → stored prediction error.

### Step 5 — MODE_A vs MODE_B vs MODE_C (real Gemini)

- Endpoint repaired this phase; previously it called `run_counterfactual_audit()` with wrong arguments, without `await`, and without any LLM caller — it could only ever return an error dict.
- With real Gemini active: **10 AI calls per audit**, structured JSON parsed, validated, and merged into decisions.
- Captured before quota exhaustion (2 businesses fully covered): **4 AI-driven decision overrides**, **14 AI manual-review participations**, 0 constraint rejections of valid AI output.
- Remaining businesses: triage ran (4 items each), provider returned 429 → circuit breaker opened → deterministic fallback. **Graceful degradation verified under real provider failure.**
- Full 5/5 coverage: **QUOTA-BLOCKED** (see §7).

### Step 6 — Real Playwright (`frontend/e2e/`, Chromium headless) — **19/19 PASSED (17.5s)**

Executed against the live stack at localhost:3000 with a seeded owner account:

| Suite | Tests | Result |
|-------|-------|--------|
| auth.spec.ts (unauthenticated) | 3 | PASS |
| navigation.spec.ts (auth redirects) | 4 | PASS |
| dashboard.spec.ts | 2 | PASS |
| upload.spec.ts | 2 | PASS |
| money-audit.spec.ts | 2 | PASS |
| owner-journey.spec.ts | 1 | PASS |
| **business-decision-loop.spec.ts** (Money Map → Top Decisions → Time Machine → approve/reject ×15 buttons → compare scenarios) | 5 | PASS |

Test infrastructure hardened during this phase: one-login `storageState` setup project (respects backend's 5-login/5-min rate limit), Arabic-first UI selectors (`button[type=submit]`), drag-drop-aware assertions, strict-mode-safe locators.

### Regression Safety

- Backend unit/integration suites re-run inside the rebuilt container after every fix: **112 passed** (34 V1 loop + 59 V8 comprehensive + 15 adversarial + 4 infra).
- Frontend production build compiles (Docker multi-stage build succeeded after fixing a TS error).

---

## 3. Real Defects Found by the Reality Test (all fixed)

V1's "108 passing tests" missed every one of these because they unit-tested services while bypassing routers and real infrastructure:

1. **Health endpoints blocked the event loop** — synchronous Celery inspect broadcasts (up to 3×5s) ran inline; under the Docker healthcheck's periodic probes, `/ready` degraded to **230+ seconds** and even `/live` timed out. Fixed: single broadcast, 2s timeout, `asyncio.to_thread`. Result: `/ready` **230s → 2.2s**.
2. **Execute endpoint never executed anything** — its supported-type path was dead code stranded after a `return` (and inside a different function body). First real call crashed: `_recalculate_audit_totals` referenced but never defined. Fixed: path restored, helper implemented, ActionExecutor invoked.
3. **ab-compare endpoint was structurally broken** — wrong function signature, missing `await`, no LLM caller, plus a missing `settings` import. Would have returned an empty error dict on every call.
4. **Outcome persistence written against an imagined schema** — V1 inserted `action_type/predicted_impact_sar/metadata_json` columns that do not exist in `outcome_feedback` (real schema: `decision_type/predicted_outcome/actual_outcome/delta` JSON). Both write and load paths rewritten against the real table.
5. **Nothing ever called the persistence layer** — `OutcomeTracker.record_and_persist()` had zero callers. The OUTCOME→LEARN link did not exist at runtime. Wired into `/complete`.
6. **Missing imports / undefined names** (`Decimal`, `logger`) — guaranteed 500s on evidence/ab-compare endpoints.
7. **Reorder execution was a no-op for stockout items** — quantity defaulted to current stock (=0). Now derived deterministically: replenish-to-safety-stock, floored by supplier MOQ.
8. **Prediction error uncomputable when per-action estimates were absent** — added documented fallback chain: explicit v2 estimate → recoverable-range midpoint → audit-level risk category total.
9. **Validator semantic bug**: reorder quantities were capped at `2× current stock`, rejecting every legitimate restock for low/zero-stock items. Replaced with evidence-bounded ceiling (stock×2 ∨ velocity×60d ∨ supplier MOQ).
10. **Free-tier quota handling** — Gemini free tier is ~20 requests/**day**/model on this key. Added call pacing (`ai_call_delay_s`) so one A/B run stays far under limits; circuit-breaker degradation verified as safe.
11. **Frontend build error** — `TopDecisions.tsx` referenced non-existent `recoverable_value_low/high_sar`; caught by the first real `npm run build`.

---

## 4. Answers to the V1 Report's Open Questions

| V1 claim (uncorrected wording) | V2 runtime finding |
|---|---|
| "Playwright PASS" | Was false. Now genuinely executed: **19/19 pass**. |
| "0 blocked tests" | Was misleading. PostgreSQL/Celery/real-LLM paths were untested; several were broken (§3). |
| "Outcome tracker persists to database" | Was unit-test-only. Now proven incl. **restart survival** (P4b). |
| "Real AI not tested" | Partially closed: real Gemini produced validated structured reasoning and 4 overrides before quota exhaustion. Full-scale comparison remains open. |
| Time Machine = simulation | Agreed and unchanged: all projections remain labelled SIMULATION/ESTIMATE. |

---

## 5. What Is Genuinely Proven Now

1. The stack runs end-to-end on real infrastructure (readiness gate green across DB/Redis/Celery/API/frontend).
2. Data flows from CSV upload through Celery into PostgreSQL and produces a 12-action audit.
3. Approval → execution changes real database state, with an audit-trail record.
4. Outcomes persist with computed prediction errors and survive restarts.
5. The evidence/A-B/time-machine APIs work at runtime, not just in unit tests.
6. Real Gemini integrates through the orchestrator (structured JSON, validation, overrides) and fails safely (breaker → deterministic fallback) under provider stress.
7. The browser journey works for a Saudi-market owner (Arabic-first UI) across 19 automated checks.
8. 112 backend tests still pass after all fixes — no regressions introduced.

## 6. What Remains Unproven

1. **Does AI improve decision quality?** Only 2 of 5 businesses completed the A/B with live AI before quota death; value-add SAR scoring exists but has insufficient real-AI samples to answer the core question. **This remains the single most important open experiment.**
2. Real measured outcomes — completions use owner-reported values (simulated here); no live retailer P&L.
3. Calibration improvement over time requires accumulated completed actions beyond this run.
4. Production hardening: load, multi-tenant concurrency, secrets management, Sentry, POS/WhatsApp integrations.

## 7. Blocker for the Final Experiment

Google Gemini free tier on this project: **~20 requests/day per model** (verified via `QuotaFailure` detail: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`). Debugging consumed both flash-lite and flash buckets (~40 calls). Reset occurs at midnight Pacific (~10:00 AST).

To complete the 5/5 real-AI A/B, any one of:
- rerun `scripts/v2_step4_reality_run.py` after Pacific-midnight reset (script is now quota-aware), or
- provide a billing-enabled Google key, or
- provide a Groq key (`LLM_PROVIDER_ORDER=groq,google,mock` already supported).

---

## 8. Honest Positioning Statement

> NazmOS is a **functioning closed-loop retail decision/recovery platform, now runtime-proven through execution and outcome persistence on a real stack**. Its AI reasoning layer is real, integrated, validated, and fails safely — but the claim "*AI reasoning produces better decisions than deterministic alone*" is **not yet demonstrated at full scale** and must not be made until the quota-unblocked A/B experiment completes.

## 9. Artifacts

| Artifact | Path |
|---|---|
| Persistence proof script (11 checks) | `scripts/v2_step3_persistence_proof.py` |
| Reality run script (5 businesses + A/B) | `scripts/v2_step4_reality_run.py` |
| LLM pre-flight validator | `scripts/v2_preflight_llm.py` |
| Raw run results | `v2_reality_test_results.json` |
| Playwright suite (19 tests) | `frontend/e2e/*.spec.ts`, `e2e/auth.setup.ts` |
| Corrected V1 report | `NAZMOS_BUSINESS_DECISION_LOOP_V1_REPORT.md` |
