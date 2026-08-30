# NazmOS — AI Architecture & Feasibility Audit

> Section 14–15 of the mission brief. Evidence-based; source code is the authority.
> Verdicts: `VERIFIED` = confirmed in code + runtime-capable as coded; `PARTIAL` = implemented but requires external prerequisite not provable in-repo; `NOT VERIFIED` = claimed but no in-repo evidence.

## 1. Executive Summary

- NazmOS contains **multiple, layered AI paths**: an LLM chat/tool-calling layer (`llm_orchestrator.py` with Groq + Gemini providers), a deterministic decision/"Nazm Planner" layer, a Phase 4 decision engine, and an "OpenCode brain" path (`opencode_brain.py`) that calls an external `opencode` CLI via subprocess.
- **AI is strictly advisory everywhere.** In every path, the output of AI is validated, pushed through a deterministic decision engine, and the final action requires merchant approval (or explicit autonomy). AI never executes directly.
- The **OpenCode integration is `PARTIAL`**: it depends on a system-level `opencode` CLI binary and API keys that cannot be verified from the repo and are not provisioned by the app. It fails closed (timeout → deterministic fallback).
- **No data from the live business flows into an external chat service by default**: `LLMOrchestrator.use_mock` defaults to `True` when no `GROQ_API_KEY` / `GOOGLE_AI_API_KEY` is set, so out-of-the-box the chat layer streams canned `MOCK_RESPONSES`.

## 2. AI Component Inventory

| # | Component | File | Purpose | Status |
|---|-----------|------|---------|--------|
| 1 | `LLMOrchestrator` | `backend/app/services/llm_orchestrator.py` | Multi-provider (Groq + Gemini) chat w/ fallback, circuit breaker, streaming | `VERIFIED` (mock default) |
| 2 | `LLMRateLimiter` | `backend/app/services/llm_rate_limiter.py` | Per-provider RPM/token budget, `estimate_tokens` | `VERIFIED` |
| 3 | `opencode_brain.py` | `backend/app/services/opencode_brain.py` | Invokes external `opencode` CLI subprocess (reasoning path) | `PARTIAL` — external CLI/key required |
| 4 | `ai_gateway.py` | `backend/app/services/ai_gateway.py` | Budget-aware wrapper (25 calls/day, 10/audit defaults); marks `ai_budget.py` | `VERIFIED` |
| 5 | `ai_budget.py` | `backend/app/services/ai_budget.py` | In-memory per-process budget accounting (thread-safe) | `VERIFIED` — in-memory, resets on restart |
| 6 | `ai_response_validator.py` | `backend/app/services/ai_response_validator.py` | Whitelists decisions, extracts financials, blocks hallucinated refs, detects prompt injection | `VERIFIED` |
| 7 | `ai_reasoning.py` | `backend/app/services/ai_reasoning.py` | Evidence-reasoning for decision explanations | `VERIFIED` |
| 8 | `ai_challenge.py` | `backend/app/services/ai_challenge.py` | Contrarian-challenge mode | `VERIFIED` (opt-in) |
| 9 | `agent_tools.py` | `backend/app/services/agent_tools.py` | `AGENT_TOOLS_SCHEMA` (OpenAI tool defs) + `execute_agent_tool` (deterministic handlers) | `VERIFIED` |
| 10 | `decision_engine.py` | `backend/app/services/decision_engine.py` | Deterministic Phase 4 scoring / decision generation | `VERIFIED` |
| 11 | `nazm_planner.py` | `backend/app/services/nazm_planner.py` | Deterministic rule engine (restock/pricing/cash/flip) with scan modes | `VERIFIED` |
| 12 | `intelligence_api.py` | `backend/app/services/intelligence_api.py` | Unified `/api/v1/intelligence/*` surface (analyze/predict/reason/plan/simulate/…/execute) | `VERIFIED` |
| 13 | `intelligence_api_client.py` | `backend/app/services/intelligence_api_client.py` | In-process client wrapping `intelligence_api` | `VERIFIED` |
| 14 | `knowledge_graph.py` | `backend/app/services/knowledge_graph.py` | KG projections (action→graph, product graph, etc.) | `VERIFIED` |
| 15 | `context_builder.py`, `context_engine.py` | `backend/app/services/` | Deterministic context assembly for AI | `VERIFIED` |
| 16 | `prompt_engine.py`, `prompt_sanitizer.py` | `backend/app/services/`, `backend/app/utils/` | Prompt construction + `sanitize_user_input` | `VERIFIED` |
| 17 | `chat_memory.py` | `backend/app/services/chat_memory.py` | Per-business chat memory | `VERIFIED` |

## 3. Provider Strategy (`llm_orchestrator.py`)

- **Providers**: `https://api.groq.com/openai/v1/chat/completions` and Gemini `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` (normalized back to OpenAI shape).
- **Provider selection**: `settings.provider_order` filtered to real providers with keys present; a provider is skipped when rate-limited; circuit breaker opens after 3 consecutive failures and half-opens after 30s timeout.
- **Mock mode**: `use_mock = settings.USE_MOCK_LLM or not (GROQ_API_KEY or GOOGLE_AI_API_KEY)`. The mock streams canned `MOCK_RESPONSES` keyed by keywords (`restock`, `recovery_match`, `whatsapp`, `dead_stock`) plus a default. **Default install is mock-only** unless keys are configured.
- **Rate limiting**: `llm_rate_limiter` respects per-provider RPM (e.g. Groq free-tier 20 RPM) with retry-after backoff between 5–90s, and waits/retries on `429`.
- **Non-streaming contract** (`generate_response`, `chat_completion`) retained for recovery/chaos tests; **streaming** (`stream_response`) is the production chat path and supports tool calling in one round (then stream the follow-up).

## 4. Agent Chat & Tool Execution (`agent_tools.py` → `_provider_stream`)

Flow in `LLMOrchestrator._provider_stream`:
1. Build messages `system + sanitize(user)`, attach `AGENT_TOOLS_SCHEMA`.
2. Call provider; if `tool_calls` present and `db`/`business_id` provided:
   - For each tool call → `execute_agent_tool(func_name, func_args, business_id, db)`.
   - Append `role: "tool"` result to messages, re-call provider for the final answer.
3. If the model returns only tool calls and no prose → graceful canned reply ("I checked your business data…").

The tool execution is `VERIFIED` deterministic: `execute_agent_tool` dispatches to in-repo `agent_tools.py` handlers (business-scoped, RLS-enforced sessions). The LLM never mutates anything itself.

## 5. OpenCode Brain (`opencode_brain.py`)

Term "OpenCode" here = external `opencode` CLI (not an in-repo component).

- **Mechanism**: subprocess command (confirmed pattern in `opencode_brain.py`): locates the `opencode` binary/`opencode.cmd`, runs `opencode run --format json` with timeout (~30s), parses JSON output, applies `ai_response_validator` checks, and on ANY failure returns a deterministic fallback.
- **Prerequisites (cannot be proven from repo)**:
  - `opencode` CLI installed on the host (`PATH` or `%APPDATA%\npm\opencode.cmd`).
  - Model/provider credentials available to the CLI environment.
- **Verdict**: `PARTIAL` — implemented and wired (`services/opencode_brain.py`, referenced by AI/brains), but not runtime-verifiable without the CLI + keys; behavior is fail-closed to deterministic. **Do NOT report this as a working OpenAI-callable feature** without a runtime check.

## 6. Validation Layer (`ai_response_validator.py`)

mandatory post-AI checks — after any provider call:
- **Decision whitelist** (`ALLOWED_DECISIONS`) — AI may only propose allowed action types.
- **Financial-extraction safety**: amounts parsed/gated, no free-form invented figures.
- **Confidence bounds** and **risk flags** (`MOCK_LLM`, `PROMPT_INJECTION`, `FINANCIAL_HALLUCINATION`, etc.).
- **Evidence-barrier**: AI responses that fail validation are **discarded**, not repaired.

## 7. Where AI Money Is Actually Generated (deterministic, not cleverness)

The durable business value lives in deterministic services; AI is a presentation layer for them:
- `money_audit_service.py` (financial statements), `recovery_intelligence.py` (financial risk classification) — numbers.
- `nazm_planner.py` — actionable restock/pricing/cash suggestions with server-side autonomy.
- `decision_engine.py` — bounded score (ROI/confidence/urgency/risk).
- `ab_decision_framework.py` (A/B), `profit_optimizer.py` (pricing), `prophet_service.py` (forecast).
- `outcome_learning.py` — rejections become evidence; `learning_adjusted_action` swaps to `ALTERNATIVE_ACTIONS`.

## 8. AI Budget / Observability

- `ai_budget.py` counters are **in-process only** (no persistence) — `PARTIAL` for multi-worker accuracy; intentional for pilot.
- `agent_observability.py` + AI-call ledger (`AI_CALL_LEDGER_PATH`, V9 experiment) write JSONL traces when configured.

## 9. AI → Action pipeline (compile for Codebase Audit master doc)

```
Merchant input / scheduled scan
        │
        ▼
Context assembled (context_builder / business_memory / knowledge_graph)
        │
        ▼
AI suggestion (mock | groq | gemini | opencode CLI)   ← advisory only
        │
        ▼
ai_gateway budget check → ai_response_validator (whitelist, injection, hallucination)
        │
        ├── FAIL ───────────────► deterministic fallback (decision_engine / nazm_planner)
        │
        ▼
nazm_planner or decision_engine (deterministic gating) — NazmOS remains authority
        │
        ▼
agent_actions (pending_approval) → auth/user approval (web + WhatsApp) or auto-execute if autonomy allows
        │
        ▼
agent_action_executor.approve_agent_action →
        execution_guard (constraints) → deterministic executor (pricing/PO/transfer) or MANUAL
        │
        ▼
outcome_learning (LearnedOutcome + OutcomeFeedback) + knowledge_graph projection
```

## 10. Claim vs Reality (AI-related)

| Claim | Evidence | Verdict |
|-------|----------|---------|
| "AI generates recommendations" | `llm_orchestrator`, `ai_reasoning`, `ai_challenge`, `opencode_brain` exist and are plumbed | `VERIFIED` (mock-only by default) |
| "AI drives actual business" | Every path re-routes through deterministic gate + approval | `FALSE` by design — AI never executes alone |
| "OpenCode integration works out-of-the-box" | Requires external CLI + key; not self-provisioning | `PARTIAL` / `NOT VERIFIED` |
| "Payments / auth are safe" | Separate section — `auth.py`, `credential_vault.py`, RLS exist | See Tenant Isolation & Security sections |

## 11. Risks & Gaps

1. **External dependency `opencode` CLI unproven at runtime** — fail-closed, but a dead feature if the binary isn't installed.
2. **In-memory AI budget** resets on each process restart; multi-worker overages possible.
3. **Mock responses stated to users as branded NazmOS output** (`MOCK_RESPONSES`) could be mistaken for real analysis in a demo.
4. **`stream_response` performs a single tool-call round**; multi-turn tool loops are not supported in the streaming path.
5. **Sanitization**: `sanitize_user_input` applied before provider calls, but full SSRF/prompt-leak hardening outside chat inputs (e.g. free-text in business context) deserves audit.