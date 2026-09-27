# LLM REPORT — PHASE 2 "BEFORE" BASELINE (AI/LLM Surface Audit)

- Date: 2026-09-23
- Repo root: `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`
- Branch: `phase1-core-infra-replacements` · HEAD: `6078008`
- Purpose: document the exact AI/LLM surface that Phase 2 must preserve while a
  Jev (TypeSafe System One) adapter is added as a non-authoritative first route
  on the canonical gateway. Read-only audit — no code changed by this report.
- Evidence labels: [V] verified by reading code, [H] historical (docs/commit),
  [X] inferred.

## 1. Executive summary
- The **live** external-LLM surface is exactly TWO endpoints, both serviced by
  the single `LLMOrchestrator` (raw `httpx` REST, no provider SDKs):
  1. `POST /api/v1/chat/` — streaming chat (`CHAT_ENABLED`-gated) [V]
  2. `POST /api/v1/money-audit/{audit_id}/ab-compare` — non-streaming A/B/C
     counterfactual reasoning [V]
- The **entire `ai_gateway.reason()` → OpenCode-brain pipeline is dormant** in
  production (zero production callers); only its `budget_snapshot` telemetry is
  live (`pilot.py:11`). [V][H]
- The V11 challenge path and the `closed_loop_experiment` /
  `business_level_reasoning` modules are dormant/legacy (test-only imports). [V]
- **No Jev / SystemOne configuration exists anywhere**; the provider whitelist is
  strictly `groq | google | mock`. [V]
- The 7-field output contract
  (`decision, confidence, reasoning, evidence_ids, risk_flags,
  alternative_decision, challenge`) is enforced on all live LLM outputs via
  `ai_response_validator.validate_ai_response`; the stronger
  `output_gate.validate_ai_output` feeds only the dormant OpenCode branch. [V]

## 2. Provider transport
- Single network choke point: `llm_orchestrator.py:217`
  `httpx.AsyncClient().post(url, headers, json=json_body)`. [V]
- Groq (`_groq_chat`, `llm_orchestrator.py:227`) and Google/Gemini
  (`_google_ai_chat`, `:236`); provider order `groq,google,mock` resolvable via
  `provider_order` property (`config.py:327-330`). [V]

## 3. Live call sites (must be preserved)
| Site | Endpoint | Handler | LLM entry | Gating |
|---|---|---|---|---|
| A | `POST /api/v1/chat/` (SSE) | `routers/chat.py:230-232` | `llm_orchestrator.stream_response(...)` → `_provider_stream` → `_call_provider` | `CHAT_ENABLED` (`main.py:251-253`) |
| B | `POST /api/v1/money-audit/{audit_id}/ab-compare` | `routers/money_audit.py:793-812` | `llm_orchestrator.chat_completion(...)` → `_groq_chat`/`_google_ai_chat` (retries `:441-454`) | `AI_ENABLED` via capability flags |

Per-triage item calls: MODE B `reason_about_item` `ab_decision_framework.py:225-227`;
MODE C `:303-305` (≤2×max_ai_calls provider calls per request). [V]

## 4. Privacy boundary (must stay intact)
- `app/security/privacy_firewall.py` builds signed `ReasoningCapsule`s; all
  THREE prompt builders use the DLP-clean outbound serializer
  `capsule.for_prompt()`:
  - `opencode_brain.py:89` (dormant path)
  - `ai_reasoning.py:150` (`_build_reasoning_prompt` — LIVE via ab-compare)
  - `ai_challenge.py:145` (`_build_challenge_prompt` — dormant)
- Capsule content boundary (`capsule.py` `CapsuleBusiness` `:29-33`,
  `CapsuleItem` `:36-45`): opaque `capsule_id/request_id/nonce` + banded/business
  safe fields only; **no SKUs, product/supplier/business ids, exact SAR values,
  stock counts, budgets, margins, or outcomes** in prompts. [V]
- Upstream sanitization: `sanitize_user_input` (`llm_orchestrator.py:392,562`);
  `ai_adapter._guard_outbound` DLP-scan (`ai_adapter.py:34-37`). [V]

## 5. Output gate (must stay intact)
- `ai_response_validator.validate_ai_response` (`ai_response_validator.py:99`) —
  **live** for ab-compare results (`ab_decision_framework.py:228, 306`);
  enforces 7-field set, `ALLOWED_DECISIONS`, `ALLOWED_RISK_FLAGS`,
  `FINANCIAL_HALLUCINATION_PATTERNS`; out-of-contract/SAR-hallucinated results →
  `constraint_rejected`. [V]
- `output_gate.validate_ai_output` (`output_gate.py:109`) — dormant OpenCode
  branch only (`opencode_brain.py:363`). [V]

## 6. Config / env surface (Jev insertion point)
- AI settings block `config.py:69-107`; comment explicitly says "direct provider
  integrations (no gateway)". [V]
- `GROQ_API_KEY` `:74`, `GROQ_MODEL` `:75` (llama-3.3-70b),
  `GOOGLE_AI_API_KEY` `:76`, `GOOGLE_AI_MODEL` `:77` (gemini-2.5-flash-lite). [V]
- `LLM_PROVIDER_ORDER` `:81` with validator `:314-325` rejecting any provider
  outside `{groq, google, mock}` — **Jev will require extending this whitelist**. [V]
- `USE_MOCK_LLM` `:82` (default True; prod guard at `config.py:359`+ and
  `utils/startup_checks.py:48-52` fails FATAL if set in prod). [V]
- `AI_CALL_LEDGER_PATH` `:88` (JSONL instrumentation — reuse for Jev shadow
  captures). `AI_ENABLED` `:93`, capsule signing/TTL `:97-98`,
  `OPENCODE_RUNNER_URL` `:102-103`, `AI_OUTPUT_MAX_CHARS` `:105`, `DLP_STRICT` `:107`. [V]
- Capability flags (`ai_policy.py:35-38`): `counterfactual_audit|challenge|
  opencode_brain` → `AI_ENABLED`; `chat` → `CHAT_ENABLED`; unknown → fail-closed. [V]
- Rate limits `llm_rate_limiter.py` (Groq 30 RPM/6k TPM, Gemini 10 RPM; in-memory
  or Redis, fail-open `:179`); budget `ai_budget.py` daily=25, per-audit=10. [V]
- **Jev / SystemOne: ZERO matches across `backend/`. No setting exists.** [V]

## 7. Dormant / legacy modules (not live in production)
| Module | Status |
|---|---|
| `app/services/ai_gateway.py::reason` | Dormant — only `budget_snapshot` used by `pilot.py:11`; `reason()` called only by `tests/security/test_ai_isolation.py:350` [V] |
| `app/services/opencode_brain.py` | Dormant — reachable only via `ai_gateway.reason` [V] |
| `app/services/ai_challenge.py::challenge_deterministic` | Dormant — only via `run_v11_counterfactual_audit` (no production callers) [V] |
| `app/services/business_level_reasoning.py` | Legacy — imports only from tests [V] |
| `app/services/closed_loop_experiment.py`, `v8_business_simulator.py` | Legacy — no router import [V] |
| `app/security/master_prompt.py` | Consumed by OpenCode path (`ai_adapter.py:25`, dormant) [V] |

## 8. Implication for Phase 2 (the Jev adapter)
- Jev is ADDED as a new provider route, never as a replacement of the live sites
  above; live behavior must be byte-identical with Jev off/disabled. [X]
- Insertion requires: (a) `JevSettings` in `config.py`
  (`JEV_BASE_URL=https://system-one.dev/v1/systemone`, `JEV_API_KEY`,
  `JEV_MODEL=jev-1.13.0`, `JEV_TIMEOUT`, `JEV_SHADOW_ENABLED`); (b) extending the
  provider whitelist validator; (c) a canonical-gateway route that is
  Jev-first but NON-authoritative (deterministic decision always wins; Jev
  output validated against canonical contract sets; failure → deterministic
  + `source="fallback"`). [X]
- Privacy/capsule/output-gate boundaries above are the hard constraints the new
  route must satisfy. [V]