# Agent Instructions (NazmOS)

Guidance for AI coding agents working in this repository, mirroring the security
acceptance contract enforced by `tests/test_security_acceptance.py` and the
`tests/security/*` suite.

## The security boundary (do not bypass)

AI output is **untrusted** until the output gate validates it. The runtime
system prompt *explains* the boundary; the code *enforces* it.

- `app/security/privacy_firewall.py` builds signed `ReasoningCapsule`s that are
  the **only** thing permitted to cross to the AI. Opaque refs + banded derived
  signals only.
- Never add SKUs, product/supplier/business ids, exact SAR values, stock counts,
  budgets, margins, or outcomes to AI prompts, capsules, or logs.
- `capsule.for_prompt()` is the DLP-clean outbound serializer. All three prompt
  builders (`opencode_brain`, `ai_reasoning`, `ai_challenge`) MUST use it.

## Master system prompt & system-role delivery

- The live runtime system prompt is the 22-section **OpenCode Master System
  Prompt** (`app/security/master_prompt.py`: `MASTER_SYSTEM_PROMPT`,
  `FULL_SYSTEM_PROMPT`). It is a static constant — NEVER generated from merchant
  data and MUST stay DLP-clean (it is scanned by `ai_adapter._guard_outbound`).
- It is delivered to OpenCode as a genuine **system role**, not concatenated
  into the user message:
  - Runner: agent file `/app/agents/nazmos-brain.md`, invoked via
    `opencode run --pure --agent nazmos-brain` (`opencode_runner/server.mjs`).
  - Subprocess: `OpenCodeSubprocessTransport._render_agent()` writes a temp
    agent .md, invoked the same way (`app/security/ai_adapter.py`).
- The agent frontmatter denies ALL tool permissions (pure reasoning). Do not grant
  any `allow`/`ask` permission on this agent.
- Output contract is normalized to the enforced field set (see
  `app/security/output_gate.py` / `ai_response_validator.py`):
  `decision, confidence, reasoning, evidence_ids, risk_flags,
  alternative_decision, challenge`. The prompt uses `evidence_ids` (not
  `evidence_refs`). Keep prose in sync with those field names.
- When editing `master_prompt.py`, run `tests/security/test_master_prompt.py`
  to confirm DLP-cleanliness and field-name sync, then rebuild the runner image
  (the agent .md is baked at build time) and the backend.
- If a new sensitive column is added, it must remain OUT of the master prompt
  prose; rely on the capsule DLP wrapper instead.

## Field-level encryption (Phase C)

Sensitive columns use `EncryptedText()` from `app/database/encryption.py`, which
stores a Fernet token in a `bytea` column and transparently decrypts on read
(with a legacy-plaintext fallback). Currently applied to
`users.two_factor_secret`. When adding a new sensitive column:
1. Use `EncryptedText()` on the model.
2. Add a migration chaining the current head that alters to `LargeBinary` with
   `postgresql_using="<col>::bytea"` plus an idempotent plaintext→cipher backfill.
3. Rebuild the `migrate` image and run it against the local compose stack, then
   rebuild/recreate the backend container.

## Secrets & logging (Phase D)

- `app/utils/logger.py` `configure_global()` attaches PII redaction to the root
  logger, uvicorn (access + error), and structlog. Call it before any logging.
- `app/services/security_audit_service.py` writes durable events to
  `security_events` / `ai_reasoning_requests` (best-effort; audit friction must
  never block a decision). `_scrub_detail` is an allowlist — never extend it with
  free-text or merchant data keys.
- `app/security/ai_policy.py#audit_event` remains a sync log-only hook; the async
  AI entry points call the durable service.

## Tenant isolation (Phase B)

- `app/middleware/rls_tenant.py` sets Postgres RLS **only** from a
  token-validated tenant id.
- `app/routers/inventory.py` restock requires `assert_business_access`.
- `app/routers/pos_webhooks.py` `resolve_webhook_business` accepts a webhook only
  when an active `POSConnection` exists for the claimed provider, and sets RLS
  only after positive tenant resolution (with teardown).

## Tests & verification

- Backend unit tests: `cd backend && python -m pytest tests/security tests/phase4 -q`
  (DB-free).
- Full acceptance (needs Postgres): set `DATABASE_URL` to a migrated DB then run
  `python -m pytest tests/test_security_acceptance.py`.
- Before finishing a change: `cd backend && python -m compileall -q app tests`
  and run the security acceptance + isolation suites.
- Migrations must be applied to the local stack via the rebuilt `migrate` image;
  `docker compose exec -T postgres psql` verifies schema at rest.
- Pre-commit / CI gates: `.pre-commit-config.yaml` (bandit + gitleaks) and
  `.gitleaks.toml`.
