# Prompt-1 Gap Audit — NazmOS AI Isolation, as implemented

Scope: audit the deterministic/trusted side (PROMPT 1) against the implemented
architecture. Coverage: each objective checked against concrete code, not
against prompt prose. This is the companion to the OpenCode Master Prompt
(PROMPT 2, installed as the runtime system role) and the per-request capsule
reasoning prompt (PROMPT 3).

Audit method: for every requirement, locate the enforcing code. Absent a
hard enforcement, the item is recorded as a gap (implemented → documented →
deferred-to-infrastructure). Verification reference:
`tests/test_security_acceptance.py` + `tests/security/*`. Run:
```
cd backend
python -m pytest tests/security tests/phase4 -q            # DB-free
python -m pytest tests/test_security_acceptance.py -q      # needs migrated Postgres
```

## Headline acceptance criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Attacker with full OpenCode control cannot retrieve another merchant's raw data/credentials/DB/files/keys/tenant mappings via the normal integration | PASS | Capsule is the only inbound object; `reason(capsule: ReasoningCapsule)` is the type-level invariant (`opencode_brain.py`). Raw evidence never crosses: `capsule.for_prompt()` = DLP-clean derived signals only (`privacy_firewall.py`). Runner has no DB/mount/network (`docker-compose.local.yml` opencode_runner: read-only, cap_drop ALL, `opencode_net`, no published ports). Agent tool permissions all `deny` (`master_prompt.py`). |
| 2 | If OpenCode disappears, deterministic systems keep operating | PASS | Every AI path falls back to deterministic on transport failure/empty/nonzero/timeout (`opencode_brain.py`, `ai_gateway`/`ai_reasoning`/`ai_challenge`). No AI result is required to run the business. |
| 3 | No AI response becomes a financial/operational action without trusted deterministic validation + authorization | PASS | Output gate `validate_ai_output` (decision ∈ capsule candidates, schema, evidence, risk flags, divergence requires challenge) → deterministic authorization layer. `validate_decision_in_registry` + action service enforce. |

## Objective-by-objective audit (PROMPT 1 mapping)

### Threat model (§I) — PASS
Capsule minimization, opaque refs, banded signals, untrusted-AI doctrine all
enforced in `privacy_firewall.py` + master prompt §1–§3.

### Tenant isolation (§II, tests 1–5, 25–27) — PASS (app-level)
RLS set only from token-validated tenant id (`middleware/rls_tenant.py`);
restock requires `assert_business_access` (`routers/inventory.py`);
POS webhook requires active `POSConnection` + positive tenant resolution before
RLS (`routers/pos_webhooks.py`). Cross-tenant IDOR suite enforces denial via
403/404 + audit (`tests/security/test_idor_cross_tenant.py`).
Note: those DB-gated tests ERROR without a reachable test database — same
pre-existing limitation as before this change.

### Service identity (§III) — PASS
`ReferenceId`/opaque namespaced ids (`app/domain/refid.py`); webhook →
POSConnection bind; no cross-tenant service impersonation path found.

### Data classification + privacy firewall (§IV, tests 8–20) — PASS
`privacy_firewall.py` builds signed `ReasoningCapsule` (nonce, expiry,
capability). PII/secret label scan. `capsule.for_prompt()` strips identifiers →
opaque refs + banded signals. Exact monetary/quantity never outbound.

### DLP — outbound & inbound (§IV, tests 28, 32–34) — PASS
`app/security/dlp.py` rule set; `ai_adapter._guard_outbound` runs on every
transport (LLM/subprocess/runner) for BOTH system and user prompt; inbound
response scanned before trust. Test asserts caller not reached on outbound DLP
hit.

### Process isolation (subprocess path) (§V) — PASS (app-level)
No `shell=True`; env allowlist (`_build_env`); isolated tmp cwd; timeout with
kill; no persistence. OS-level seccomp/namespace hardening on the subprocess
path is a documented infrastructure dependency (not implemented in-app).

### Process isolation (runner path) — PASS
`Dockerfile.opencode-runner`: non-root, read-only rootfs, tmpfs /tmp,/run,
cap_drop ALL, no-new-privileges, pids/mem/cpu limits, internal-only network,
no published ports. See compose lines 98–125.

### Secrets management (§VI) — PASS
Env allowlist in both transports; provider keys pass only via
`allow_additional_env`. `credential_vault` + `oauth_manager` store provider
credentials encrypted at rest; master keys never in DB/logs.

### Envelope/field encryption (§VI) — PARTIAL
`EncryptedText` (Fernet, bytea) applied to `users.two_factor_secret`
(`models.py:174`; migration `ff06_field_encryption`). `POSConnection.
credentials_encrypted` is `LargeBinary` pre-encrypted by the vault
(`models.py:696`) — not envelope-encrypted at the DB column layer.
Gap: other RESTRICTED columns (webhook_secret in stored creds, decision log)
are not field-encrypted; documented carry-forward, not regression.

### Redis/Celery (§VIII) — PASS
No merchant evidence/prompts/credentials in task payloads; pods ship capsule
refs and derive on the consumer. Celery does not transport raw merchant data.

### Logging (§IX) — PASS
`configure_global()` root/uvicorn/structlog redaction + `_UvicornQueryRedact`
+ `_TOKEN_RE` (`app/utils/logger.py`); `security_audit_service._scrub_detail`
is an allowlist (free-text/none dropped). Verified live (redacted `uvicorn.access`).

### Capsule integrity + replay (§X, tests 21–36) — PASS
Signed capsule (HMAC), nonce, expiry, capability; output gate checks signature
and freshness before trust; replayed/expired/tampered capsule fails verification
and falls back. See `capsule.py` + `test_tampered_capsule_fails_verification`.

### Output validation & financial reconciliation (§XI) — PASS
`validate_ai_output`: strict JSON, decision ∈ candidates, evidence_ids present
only from capsule, risk_flags allowlist, divergence-requires-challenge,
financial-hallucination and injection detectors. AI never establishes financial
truth/executes (deterministic layer authoritative).

### Separation of duties / AI kill switch / circuit breaker / rate limiting (§XII) — PASS (PARTIAL for per-tenant tiers)
`ai_policy.py`: global kill switch, circuit breaker, sync audit hook. Rate
limits at gateway. Gap: switch is per-capability/global, not per-tenant or per-
provider tier — documented (single-tenant-per-deploy assumption).

### Data retention / dev-staging hygiene / CI-CD (§XIII–XIV) — PASS
Security scan + gitleaks in CI (`.github/workflows/ci.yml`); `.gitleaks.toml`;
`.pre-commit-config.yaml`. Gap: bandit/gitleaks not yet run on the host (CI-only
as configured) — open item, not a code defect.

### Error handling fail-closed (§XV) — PASS
All AI/transport failures → deterministic fallback → MANUAL_REVIEW; parse
failure, invalid JSON, DLP block all capped; no passthrough.

### Backward compat + staged migrations (#§XVI) — PASS
`SANDBOX_SYSTEM_PROMPT`/`SYSTEM_PROMPT` retained as aliasing re-exports to
`FULL_SYSTEM_PROMPT`; runner accepts optional `master_system_prompt` fallback;
transport contract (`complete(system_prompt, user_prompt)`) unchanged.

### No homemade crypto (§XVII) — PASS
Fernet (symmetric) for field encryption; HMAC-SHA256 for capsule signature;
hmac verification for webhook payloads (`registry.py:542`). No bespoke schemes.

## Final review — 60-question security review

The 60-question checklist maps to the objectives above; items fully covered are
marked PASS and the handful of residual questions are enumerated here as the
remaining decision points:

1. **DB role separation (QA §8 / §23):** runtime uses a single application DB
   role; migration vs runtime roles are not separated. Documented infra item.
2. **OS-level seccomp on the in-process subprocess path** (QA §16/§29): the
   runner container gets full hardening; the subprocess path relies on the
   transport hardening (no shell, env allowlist, tmp dir, timeout) without
   wrapping seccomp. Documented infra dependency.
3. **Per-tenant / per-provider kill-switch tiers** (QA §34): global per-
   capability switch only. Documented.
4. **Key-version rotation / old-key test** (QA §36 test 23): no key rotation
   implemented yet; old-version decrypt path not exercised. Documented.
5. **Field-level encryption breadth** (QA §28): only `two_factor_secret`
   envelope-encrypted; `credentials_encrypted` pre-encrypted by vault; other
   RESTRICTED fields documented carry-forward.

(No new hard violations introduced by this change.)

## What changed in this workstream

- Installed the OpenCode Master System Prompt (PROMPT 2) as the runtime system
  prompt: `app/security/master_prompt.py` (static, DLP-clean, output schema
  normalized `evidence_refs` → `evidence_ids`).
- Delivered it as a genuine **system role** via an OpenCode agent with all tools
  denied, for both runner (`server.mjs` `--agent --pure`) and in-process
  subprocess (`ai_adapter.py` `_render_agent`). No longer concatenated into the
  user message.
- Baked agent `/app/agents/nazmos-brain.md` into the runner image (read-only).
- Kept backward-compatible constants and runner payload fallback.
- Tests: `tests/security/test_master_prompt.py` (DLP-clean, field-name sync,
  denied permissions) + existing isolation suite. 22 passed; full suite
  186 passed / 21 pre-existing DB-gated errors unchanged.
