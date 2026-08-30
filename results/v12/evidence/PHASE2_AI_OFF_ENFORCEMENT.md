# V12 PHASE 2 — AI-OFF Enforcement + External Proof

Timestamp: 2026-08-27 ~14:40 UTC
Scope: prove ZERO AI/LLM provider calls and NO mock-AI during the entire V12 deterministic reality test.

## Why there is no single "AI off" switch
The codebase has no single env that disables AI. The AI layer is invoked only through a few
entry points, and the orchestrator (`LLMOrchestrator`) decides at construction time:

```
use_mock = settings.USE_MOCK_LLM or not (GROQ_API_KEY or GOOGLE_AI_API_KEY)
_real_providers() = [p for p in settings.provider_order if p in ("groq","google")]
```

- `use_mock=True`  -> chat_completion returns a canned "MANUAL_REVIEW" mock (forbidden by V12).
- `_real_providers()` non-empty + keys -> real Gemini/Groq HTTP POST (forbidden by V12).

## Hard-disable configuration (applied)
`.env` and `docker-compose.local.yml`:

- `LLM_PROVIDER_ORDER=mock`  (only non-real provider token the validator accepts; empty resets to default)
  => `provider_order == ['mock']` => `_real_providers() == []`
- `USE_MOCK_LLM=false`        (keeps `use_mock` from flipping to True)
- `GOOGLE_AI_API_KEY` / `GROQ_API_KEY` left PRESENT only so `use_mock` stays False; they are never consulted.
- `AI_CALL_LEDGER_PATH=/app/tmp/v12_ai_calls.jsonl` (fresh, empty, V12-specific)

Net effect AT THE ORCHESTRATOR:
- `use_mock == False`      (no canned mock output)
- `_real_providers() == []` (zero providers iterated => zero HTTP, even if invoked)

Verification from the running backend container (python, live):

```
USE_MOCK_LLM= False
LLM_PROVIDER_ORDER= mock
provider_order= ['mock']
real_providers= []
use_mock= False
_real_providers= []
```

## Deliberate probe (proves the safety net)
We invoked the AI completion path **on purpose** to prove it cannot reach a provider:

```
o = LLMOrchestrator()
r = await o.chat_completion('system','probe...')
=> returned None, elapsed 0.005s, total_requests_attempted=1
```

- Leading ledger record: `{"provider":"none","outcome":"all_providers_failed",...}`.
- NO `provider:google`/`provider:groq`, NO `outcome:ok`, NO `provider:mock`.

=> Even a stray AI invocation yields `all_providers_failed` with zero provider network I/O
and zero mock output. Proof saved as `0_ai_off_PROBE_ledger_proof.jsonl`.

## Scope of "the deterministic product under test"
Confirmed via source inspection (`decision_engine.generate_decision`, `money_audit_service`,
`ab_decision_framework.deterministic_decision_for_item`, `action_executor`, `constraint_service`):
the owner-facing deterministic flow (upload -> money audit -> findings/actions -> approve/execute)
does NOT invoke the LLM. The `_enrich_audit_with_intelligence` enrichment calls
`intelligence_api.analyze` -> `decision_engine.generate_decision`, which is **fully deterministic**
(rule-based candidate generation + scoring; `parse_llm_decisions` only parses externally-supplied JSON).

The true AI surfaces (ab-compare's `chat_completion`, chat `stream_response`,
`ai_reasoning`/`ai_challenge` via llm_caller) are NOT exercised in V12 and, per the probe above,
cannot reach a provider anyway.

## Zero-AI ledger enforcement
- Baseline ledger (V11 residue, 4190 records incl. rate-limit errors) archived to
  `results/v12/evidence/v11_ledger_BASELINE.jsonl`.
- V12 ledger `/app/tmp/v12_ai_calls.jsonl` reset to 0 bytes (clean).
- After EVERY V12 phase, the ledger is re-checked and must contain zero records.
- Any v12 ledger entry that is `provider:google/groq` or `outcome:ok` or `provider:mock`
  => CRITICAL FAIL.

## Independent observation (belt-and-suspenders)
- Backend `.env` set; container recreated (`docker compose up -d`); config re-verified live inside the container.
- DB schema at head `ff01_owner_const` (alembic current).
- The `provider_order`/`_real_providers()` live introspection above is the strongest proof and
  is recorded verbatim in this file.
