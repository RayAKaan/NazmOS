# JEV_FEASIBILITY_REPORT.md

**Can NazmOS use Jev? — Verified answer: yes, as a decision adviser, with guardrails.**

Compiled from independent web research (2026-09-20) and direct probing of the local `jev-mvp` containers. Evidence labels: [V] verified (web research corroborated by ≥2 independent sources, or directly probed locally), [U] unverified at this time, [B] blocked/unavailable.

## 1. What Jev is (verified)

Jev is **TypeSafe AI's "System One" model** — a structured-evaluation model, released 2026-09-15, currently **early access (waitlisted)**. It does **not** generate text; it reads application state and returns **typed, schema-constrained decisions** in 70–500 ms. [V]

- Docs/portals: docs.typesafe.ai, jevapi.dev, Jev by TypeSafe AI (jevtypesafeai.com), OpenRouter partner page, Cloudflare AI docs (`typesafe/jev`), Experiential Cloud; independent write-ups: OpenTweet, Julian Goldie. [V]
- SDKs: Python + JS (`@typesafe-ai/sdk`), reads `TYPESAFE_API_KEY`. [V]
- Sole native endpoint: `POST https://api.typesafe.ai/v1/systemone` with body `{ model, state, questions }`. [V]

## 2. The three typed primitives (verified shapes)

| Primitive | Question | Request shape | Answer fields | Limits |
|---|---|---|---|---|
| **Choice** | "Which one of these options?" | `criteria`: map option→description | `choice` (your key), `probabilities` (sum 1.0), `confidence` | up to 255 options |
| **Score** | "Which level on this ordered scale?" | `criteria`: **ordered array** of 2–10 level descriptions | `score` (probability-weighted mean of level indices), `legend`, `probabilities`, `confidence` | 2–10 levels; no min/max semantics |
| **Noul** | "Is this statement true?" | `instructions` as a **statement**; optional `criteria` {true,false} | `noul` float 0–1 **only** — no confidence field | — |

Parallel evaluation: all questions in a request are answered in ONE pass over ONE shared `state`; answers are independent (never chained). [V]

Response: `{ "model": "jev-1.13.0", "answers": {<questionKey>: {...}}, "usage": {"input_tokens": N, "output_tokens": M} }`. Model alias `jev-latest` exists; **pin a version (`jev-1.13.0`) in production** because thresholds drift when the alias moves. [V]

## 3. Pricing & limits (vendor-stated)

- **$0.042 / M input tokens; output tokens free** ($0/M). About 1/48th of GPT-class input pricing. TypeSafe concedes pricing sustainability is not yet proven and the "not subsidised" claim is unverified. [V]
- Context ≈ 32k–64k input tokens (state + all questions). [V]
- Rate limits (TypeSafe-native): 250,000 tokens/sec and 1,200 requests/min. [V]
- Third-party gateway bounds (Experiential): ≤32 questions/request, ≤64 options per Choice, 2–10 Score levels. [V] OpenRouter + Cloudflare each host it with their own limits.
- Cost model for NazmOS: token cost is driven by the `state` you send; keep state small (DLP-banded signals, not full history). [V]

## 4. Honest limitations (critical for design)

- **Schema-constrained ≠ hallucination-free.** Jev can assign high confidence to a wrong-but-valid option. TypeSafe's own launch text concedes the "zero hallucination" figure "is not empirical"; the CEO repeated this on Hacker News. **Consequences: risk_flags/uncertain handling + deterministic override are mandatory.** [V]
- **No rationale.** Answers carry probabilities/confidence, not reasoning — a known audit/compliance limitation. NazmOS governance requires `reasoning` in the output contract; Jev cannot fill it natively → the deterministic decision path supplies reasoning. [V]
- **No arithmetic reliability** — don't ask it to count or do date arithmetic (our deterministic core does that). [V]
- **Independent questions, shared state** — do not assume Question A feeds Question B. Compose accordingly (fan-out is cheaper anyway: 13-question fan-out measured 12.2x cheaper / 10x faster than one-at-a-time). [V]
- **Early access / waitlist** — account provisioning may be gated for some time; API moves fast (early-access). Phase 2 must be behind a config flag and mock-tested from day one. [V]
- **Confidence is not accuracy** — set thresholds from your own labelled ground truth; keep a dead band middle. [V]

## 5. Fits NazmOS decision surfaces (summary)

- recovery.rank / action_type / root_cause_bucket → **Choice** — ideal fit (switch-on-key contract). [V]
- stockout tier / supplier risk / reorder urgency / margin erosion → **Score** — ideal fit for urgency/rubric ranking; calibration target = deterministic tier/`gross_margin_pct`. [V]
- anomaly/finding flags → **Noul per flag** — ideal for independent booleans; remember Noul has NO confidence field, threshold it yourself. [V]
- Never: Shariah triage, owner-band gating, cash-action priority, approval routing (governance/money-critical → deterministic). [V]

## 6. Local resource: `jev-mvp` containers (VERIFIED ON THIS MACHINE)

Two running containers, image `jev-support-mvp:latest`, up at audit time:
- `jev-mvp` → `0.0.0.0:8000`, `jev-mvp-pg` → `0.0.0.0:8001` (both map to container port 8000, uvicorn `app.main:app`). [V]
- Both expose a FastAPI app titled **"JEV Support Decision Infrastructure"**, version 0.2.0 (`/docs`, `/openapi.json` return HTTP 200). [V]
- Exposed paths (from `/openapi.json`, pruned): `/health`, `/ready`, `/v1/metrics`, `/v1/decisions`, `/v1/outcomes`, `/v1/providers/{provider}/webhook`, `/v1/decisions/{decision_id}`, `/v1/evaluate`, `/v1/actions`, `/v1/actions/{id}`, `/v1/actions/{id}/transition`, `.../dispatch/prepare`, `.../dispatch/prepare-with-evidence`, `.../execute`, `.../reconcile`, `/v1/org/evidence`, `/v1/org/entities/.../evidence`, `/v1/decisions/coupling`, `/v1/org/simulation`, `/v1/org/evidence/assess`, `/v1/org/decisions/evidence-gate`, `/v1/tickets/resolve-plan`, `/v1/tickets/verify-resolution`. Component schemas include `DecisionRequest`, `DecisionResponse`, `Action`, `CandidateAction`, `RiskLevel`, `Signals`, `Ticket`, `EvidenceRequest`, `OutcomeEvent`, etc. [V]
- Note: this local app is a Jev-*support* decision infrastructure, not the TypeSafe `/v1/systemone` model endpoint itself; treat it as a **local integration/mock resource** for building the Jev adapter in Phase 2. Its exact contract vs. TypeSafe is not yet mapped (no local schema diff performed). [I]
- No `TYPESAFE_API_KEY` / `jev` / `systemone` configuration exists in `backend/` today (grep). [V]

## 7. Feasibility verdict

**GREEN with conditions.** Jev is real, documented, cheap, and a strong structural fit for the 8 batched decision surfaces. Integration is non-blocking because:
1. The deterministic funnel (`ab_decision_framework.deterministic_decision_for_item`) and canonical financial core are independent of Jev; Jev is purely additive shadow evidence. [V]
2. The AI choke point (`ai_gateway.reason`) is dormant in production → extending it with a `systemone` transport cannot disturb the live Groq/Gemini chat path. [V]
3. A local mock (`jev-support-mvp`) is already running for development. [V]

**Entry conditions before Phase 2:** (a) Phase 1 foundation (repo compiles, all gates green, 2B/2C accepted); (b) Jev account/API key (early-access waitlist — start immediately); (c) decision to pin `jev-1.13.0` + threshold labelling harness; (d) policy decision: gateway becomes the Jev entry point (recommended) vs. wire production AI through the gateway.

**Unverified / blocked for now [U][B]:** actual TypeSafe account provisioning status, exact current API schema drift, whether the local `jev-support-mvp` mirrors native TypeSafe request/response (needs diffing against docs in Phase 2), and output-token-metering details (no impact — output free).