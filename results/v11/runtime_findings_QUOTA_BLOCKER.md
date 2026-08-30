# V11 Reality Test — Runtime Investigation Findings & Blocker

**Date:** 27 Aug 2026 19:44 local (14:44 UTC)
**Status:** BLOCKED — All free-tier AI daily quotas exhausted
**Verdict status:** NOT VALIDATED (insufficient real-AI data to emit A/B/C/D)

---

## 1. Objective (recap)
Empirically determine whether contextual AI produces materially better retail
decisions and financial outcomes than the deterministic engine alone, using
**real** LLM calls (never simulated), a frozen ground truth, and a deterministic
control group.

---

## 2. Executive Blocker Summary
The V11 runtime experiment cannot complete **right now** because every real AI
provider configured for the sandbox has exhausted its **free-tier daily quota**
as a direct result of our own testing/iteration. A partial run (real AI where
quota allowed, deterministic elsewhere) would compromise the experiment's core
requirement (real AI everywhere it is meant to run), so per the non-negotiable
rule "no fabricated results / no simulated AI in the primary experiment", we are
**stopping** rather than faking data.

---

## 3. Provider Quota State (measured, not assumed)

### 3.1 Google — `gemini-2.5-flash` (primary)
- **Error observed:** `429 RESOURCE_EXHAUSTED`
- **Metric:** `generativelanguage.googleapis.com/generate_content_free_tier_requests`
- **Hard daily limit:** `20` requests/day for this model
- **Status:** EXHAUSTED — every call in the last hour returns 429 even after 60–75s idle
- **Reset:** tied to the model's free-tier daily window (Google, typically resets at
  midnight Pacific = ~08:00 UTC next day, ~14 hours away)

### 3.2 Google — `gemini-2.5-flash-lite` (fallback)
- Same `generate_content_free_tier_requests`, limit `20`/day
- **Status:** EXHAUSTED. Demonstrated behavior: worked ~5–7 back-to-back calls
  (incl. one full challenge that returned valid JSON), then permanently 429 even
  after 75s of complete idle with no other traffic — concluding it is a *daily*
  cap, not a recoverable RPM window.

### 3.3 Groq — `openai/gpt-oss-120b`
- **Error observed:** `429` — `Rate limit reached for model openai/gpt-oss-120b ...
  on tokens per day (TPD): Limit 200000, Used 199095, Requested 1242`
- **Hard daily limit:** `200,000` tokens/day on TPD
- **Status:** EXHAUSTED (199,095 / 200,000 used)
- **Reset:** midnight UTC (~23:00 local, ~9 hours away)

### 3.4 Groq — other candidate models
- `llama-3.3-70b-versatile`, `qwen/qwen3-32b`, `meta-llama/llama-4-scout-17b-16e-instruct`,
  `llama-3.1-8b-instant` all returned `404` ("does not exist or no access") on the
  current Groq account. Only `openai/gpt-oss-120b` (and other gpt-oss / qwen3.6-27b
  family) are accessible, and they share the exhausted org-level token budget.

---

## 4. Root Cause of Quota Exhaustion
- The dominant consumer of quota was **our own iterative debugging** (many single
  and batched test calls across two Google models plus Groq), not the experiment
  itself.
- Google free-tier is extremely small (20 req/day/model). We burned ~20 on
  `gemini-2.5-flash` and ~20 on `gemini-2.5-flash-lite` across connectivity tests.
- Groq org-level TPD (200K) was consumed by batched test calls and repeated
  experiment attempts (each challenge prompt is ~1,200–2,400 tokens).

---

## 5. What DID Work (verified positive findings)

### 5.1 Full end-to-end AI pipeline is functionally correct
A real challenge through the complete stack
(`LLMOrchestrator` → `BusinessContextEngine` → `ai_challenge.challenge_deterministic`
→ validation) returned a **valid, well-reasoned challenge**:

```
status: CHALLENGE
proposed_decision: DO_NOTHING
confidence: 0.8
reason: "The deterministic decision is to DISCOUNT, but the product has a
        gross margin of 0.0%. Discounting an item with no margin will result
        in a direct loss..."
challenge_status = ChallengeStatus.CHALLENGE
is_valid = True
```

- The AI correctly identified that discounting a zero-margin DEAD item is
  financially self-defeating and proposed `DO_NOTHING` — a materially more
  sensible recommendation than the deterministic `DISCOUNT`.
- **This is the strongest provisional evidence that AI *can* add value** — but it is
  a single demonstration, not a statistically sound A/B comparison, so it cannot
  by itself justify a verdict.

### 5.2 Groq works for a single call
`openai/gpt-oss-120b` returned a 2,400–2,600 char structured markdown analysis for
a test prompt (availquota permitting).

### 5.3 Config plumbing verified
- `.env` → container env injection works via `docker-compose.local.yml`
  (`GROQ_API_KEY`, `GOOGLE_AI_API_KEY`, `LLM_PROVIDER_ORDER`, `GOOGLE_AI_MODEL`,
  `GROQ_MODEL` all propagate).
- `docker-compose` env vars (not the in-container `.env` file) are the source of
  truth; verified we must `docker compose up -d backend` to apply changes.
- `provider_order: ['google', 'groq', 'mock']` and `USE_MOCK_LLM=false` verified.

### 5.4 Rate limiter and circuit breaker behave as designed
- `llm_rate_limiter` correctly tracks rpm/tpm/rpd in Redis (`flushdb` resets it).
- The circuit breaker opens after `failure_threshold` consecutive provider failures
  and gracefully falls back (returns `None` → deterministic path). This is the
  intended safety behavior — it correctly prevented the system from hanging.

---

## 6. Fixes Applied During This Investigation (must not be lost)
1. **`evidence_package.py`** — Docker image was stale (no `seasonal_type`/V11 fields);
   re-copied into container. Verified `seasonal_type` + `ghost_po_risk` present.
2. **`ab_decision_framework.py`** — re-copied to container.
3. **`llm_orchestrator.py`** — added per-provider rate-limit **retry with backoff**
   inside `chat_completion` (waits `backoff_until`-derived seconds then retries the
   same provider up to 2 extra times) instead of instantly cascading to failure.
   **NOTE:** my earlier experiment-adapter retry loop (8s/15s sleeps) was reverted —
   do not re-add; the orchestrator-level retry is the correct home.
4. **`llm_rate_limiter.py`** — corrected Groq limits to reflect reality:
   `rpm:30, tpm:8000, rpd:1000` (was tpm:6000, rpd:14400), Google `rpm:20`.
5. **`.env`** — final state:
   - `GOOGLE_AI_MODEL=gemini-2.5-flash-lite` (chosen because its quota was the
     most recently demonstrably working; switch to a fresh/paid key when available)
   - `GROQ_API_KEY=<gsk_...>` provided by user
   - `LLM_PROVIDER_ORDER=google,groq,mock`
   - `USE_MOCK_LLM=false`
6. **`v11_run_experiment.py`** — `MAX_AI_CALLS_PER_CHECKPOINT=8`,
   `AI_CALL_DELAY_S=4.0` (paced to stay within Google's 20 RPM / free-tier limits).

---

## 7. MOVED Configuration History (do not regress)
| Item | Was | Now | Why |
|------|-----|-----|-----|
| `GOOGLE_AI_MODEL` | `gemini-2.5-flash` | `gemini-2.5-flash-lite` | flash daily quota exhausted; lite last working |
| `LLM_PROVIDER_ORDER` | `groq,mock` → `google,groq,mock` | order = google first | prefer the provider with (currently) more usable headroom |
| `GROQ_MODEL` | — | `openai/gpt-oss-120b` | the only accessible Groq model |

---

## 8. Experiment Integrity Safeguards Preserved
- **Ground truth firewall** remains ACTIVE — GT is only used by the evaluator, never
  in decision logic, context engine, or AI prompt. Re-verified this session.
- **No simulated AI** was introduced into the primary experiment path. When both
  providers returned `None`, the pipeline fell back to deterministic (by design)
  but the experiment was **not** recorded as "real AI success" — it recorded
  `AI_FAILED_*` / fallback, which is honest.
- The single valid challenge (sec 5.1) is real; it is recorded as evidence, but
  the experiment must be re-run to completion with quota before any verdict.

---

## 9. Remaining Steps (blocked until quota resets or new key)
1. **Step 5 (re-run experiment)** — requires real AI calls. Blocked on quota.
   - Recommend waiting for Groq midnight-UTC reset (~9h) OR a fresh/paid key.
   - Current config paces at 4s/8 calls per checkpoint = within limits.
2. **Step 6 — latency test** (`v11_latency_test.py`) — must measure real latency;
   blocked on quota (needs successful real calls).
3. **Step 7 — security tests** — architecture/unit tests (18 security + 8 AI failure
   modes); *could* run now, do not strictly require live quota (they assert
   *fallback safety*). Not yet executed in this session.
4. **Step 8 — Playwright E2E** — functional owner journey; does not require LLM
   quota (run against frontend on host). Not yet executed in this session.
5. **Step 9 — metrics aggregation** — requires experiment output; blocked.
6. **Step 10 — regenerate final report** with real numbers + verdict. Currently the
   report still reads verdict **D (NOT VALIDATED)** and must be refreshed once
   runtime data exists.

---

## 10. Recommendation
Wait until **midnight UTC** (Groq TPD reset, ~23:00 local) and re-run the experiment
with `openai/gpt-oss-120b` as primary (`provider_order=['groq','google','mock']`) and
`gemini-2.5-flash-lite` as live fallback. Estimated ~96 real calls:
- 6 checkpoints × (8 Mode B + 8 Mode C challenge calls ≈ 96)
- Groq TPD (200K) reloaded and budgeted (~2K tokens/call × 96 ≈ 192K) — tight but
  feasible; set `GOOGLE` first if Groq is again insufficient.
- Pace at 4s/call to respect RPM.

If a paid/alternate API key is available, provide it and execution can resume
immediately without waiting.

---

*This document records findings; it does NOT invent results. The V11 verdict
remains NOT VALIDATED pending a complete run with real AI calls.*
