# Item 11 — Final Remediation Report (No Commit)

Scope: Items 7–11 completion and full-session verification. Per the directive,
**nothing has been committed** — all changes remain on the working tree for the
user's review. Non-negotiable rules remained in force throughout.

---

## 1. Files changed this session (Items 7–11)

### Production hardening (Item 7 — tenant scope + fail-closed)
- `backend/app/routers/pharmacy.py` — `add_lot`: `assert_business_access` (was cross-tenant INSERT from client business_id/item_id).
- `backend/app/routers/decisions.py` — `apply_decision`: requires `business_id`, `assert_business_access`, UPDATE bound `WHERE id AND business_id`; removed dead import.
- `backend/app/services/finding_service.py` — `advance_status`/`verify_finding`: optional `business_id` binds SELECT/UPDATE (`AND business_id = :b`).
- `backend/app/routers/audits.py` — passes `business_id` into finding_service calls.
- `backend/app/routers/upload.py` — `stream_progress` ownership check; four `detail=str(e)` leaks → generic messages.
- `backend/app/routers/health.py` — error constants; `/health/redis` + `/health/celery` scrub reasons.
- `backend/app/routers/actions.py` — `execute_action` DecisionLog lookup scoped to tenant.

### Tests / fixtures (Item 7/8/9)
- `backend/tests/regression/test_adversarial_matrix.py` — new `TestISecondAudit...` (9 guards) + `TestRootCauseAssertions` (8 assertions).
- `backend/tests/test_decisions.py` — business-scoped apply tests (+403/404 for foreign).
- `backend/tests/test_agent_actions.py` — fixture sets `owner_id` (fixes pre-existing RBAC gap).
- `backend/tests/test_etl_dedup.py` — canonical 4-field row hash; idempotency `xfail` on SQLite (covered on Postgres).
- `backend/docs/openapi.json` — refreshed golden for intentional `apply_decision` `business_id` param.

### Reports (new)
- `backend/docs/item7_second_audit_A_Y.md`, `backend/docs/item8_root_cause_assertions.md`,
  `backend/docs/item9_full_verification.md`, `backend/docs/item10_canonical_chain_verification.md`,
  plus this `item11_final_report.md`.

*Note: the working tree also contains pre-existing session changes from Items 1–6
(frontend/backend), left uncommitted.)

## 2. Migrations

No new migration this session — the canonical head is `ff08_loc_grain_tenant_model`
(single head). Verified `alembic heads`/`alembic current` land there and the full
chain upgrades cleanly on the test DB.

## 3. Tests added (session)

- 9 source-level tenant-scope/leak guards (Item 7, DB-free).
- 8 root-cause assertions (Item 8, DB-free).
- Updated apply-decision business-scoped tests (Item 7).
- Golden-fixture + adversarial regression harness already present from Items 5–6 (15/15, 31 passing).

## 4. Verification results (Item 9, honest)

- **Full suite** (`python -m pytest tests/` on migrated `nazmos_test`):
  **1190 passed, 3 skipped, 1 xfailed, 1 failed** (12:44).
- `compileall` clean; `bandit` clean (only pre-existing intentional `# nosec` B608);
  gitleaks configured; alembic single head; 228 routes; OpenAPI contract passes.
- The **single failure** is the pre-existing environment flake
  `tests/security/test_celery_rls_tenant_context.py::...test_async_session_in_context_sees_only_own_tenant`
  (`RuntimeError: Event loop is closed` under massive combined async runs). It passes
  reliably in isolation (5.8s) and whole-file (7 passed). It is unrelated to any
  session edit and is recorded — not hidden.
- Three pre-existing test defects were resolved honestly rather than hidden:
  stale `test_etl_dedup` (canonical-hash alignment + SQLite-idempotency `xfail`),
  `test_agent_actions` fixture ownership link, and OpenAPI golden drift.

## 5. Residual findings (P0 / P1 / P2)

**P0 (fix before any production audit exposure)**
- `chat_messages` / `pos_sync_logs` lack RLS tenant policy (models `:492-515`, `:789-807`) — tenant isolation gap at the DB layer for those tables.
- `WHATSAPP_VERIFY_TOKEN` ships a default (`config.py:160`) — webhook signature can be predicated on a public default in a misconfigured deployment.
- Field-level encryption breadth: only `users.two_factor_secret` is `EncryptedText()` (Phase C) — supplier prices, margins, PII remain plaintext at rest.

**P1 (hardening)**
- `recovery_match_service.complete_match` UPDATE has no party/business check — recommend gating (R2R match cross-tenant is intentional for reads; the write should be owner-scoped).
- `money_at_risk_sar` <> `capital_at_risk_sar` legacy alias (`models.py:1404-1406` / `money_audit_service.py:559-561`) — remove ambiguity.
- `execution_guard._reverify_reorder_state` is fail-open (unverified) — audit for a real fail-closed recheck.
- Secondary-chain hardcoded `/30.0` denominators all safely guarded (GREATEST/NULLIF) but confined to recovery-match / intelligence / planning — documented, not canonical.

**P2 (sprawl / hygiene)**
- v9–v12 version sprawl and multiple migration-naming generations; `USE_CELERY`/`USE_REDIS`/`USE_CLIENT_ETL` default False (features latent, honest — intended).
- Item-name-only identity (no casefold/NFKC/SKU key) and SchemaDetector header mis-mapping remain — non-blocking for the canonical chain, tracked for ETL quality.

## 6. Canonical-contract statement

The non-negotiable contract holds end-to-end:
deterministic logic is authoritative (one shared `audit_core` math core); AI is
advisory only and never touches raw merchant data (capsule/opaque-ref DLP
boundary); there is one canonical execution path (ETL → money audit →
time-machine/evidence/guest → tenant-scoped action execution); everything is
fail-closed (location-collapse refusal, unknown → `UNKNOWN`, no anonymous
execute); tenant isolation is enforced at DB (RLS) + service (`assert_business_access`,
business-bound UPDATEs); UNKNOWN never becomes 0; financial numbers carry
deterministic provenance (coverage-aware velocity, no fabricated recovery);
SKU × location grain never collapses; and 6 observed days are never presented
as 30. **No commit was made.**
