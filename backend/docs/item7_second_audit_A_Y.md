# NazmOS Second Codebase Audit (A–Y) — Item 7

Date: 2026-09-07
Scope: `backend/app/routers/*` (33 files), `backend/app/services/*` (~150), `backend/app/middleware/*` (13), `backend/app/tasks/*` (11), `backend/app/config.py`, `backend/alembic/versions/*`.
Method: read-only exploration of the live code, then targeted hard-fixes for confirmed live gaps. Evidence is `file:line` against HEAD of the working tree (no commit made).

Legend: **PASS** = enforced; **PARTIAL** = enforced with remaining residual risk (documented); **GAP** = confirmed hole (fixed this session where live, or documented where latent/infrastructure).

---

## A–H — previously audited (Items 1–6), still green

| Dim | Area | Verdict | Evidence / tests |
|-----|------|---------|------------------|
| A | Cross-tenant / IDOR | PASS | `tests/security/test_idor_cross_tenant.py`; `money_audit.py:236-407` double-gates; `agent.py:86-296` access+capability |
| B | AI KPI fabrication | PASS | `tests/regression/test_chat_no_fabricated_kpis.py` (18); `opencode_brain.py` BrainDecision carries no financial fields |
| C | Capsule / DLP | PASS | `privacy_firewall.py` + `capsule.for_prompt()`; DLP outbound+inbound; master prompt DLP-clean |
| D | Input-side injection / baked agent file | PASS | `tests/regression/test_adversarial_matrix.py::TestDBakedAgentFileHygiene`; agent frontmatter all-deny |
| E | Anonymous execution | PASS | E class in adversarial matrix; every production `execute_action` call passes attested `user_id` |
| F | UNKNOWN→0 / silent downgrade | PASS | F class + `audit_core.coverage_aware_daily_velocity`; coverage-aware velocity every chain |
| G | Location grain collapse | PASS | `etl_pipeline._apply_inventory_snapshot` fail-closed guard + DB-backed G test |
| H | Reporting denominators | PASS | H class; `COUNT(DISTINCT DATE(...))` in `audit_engine.py` stockout scan |

---

## I–Y — second-audit dimensions (this session)

### I) Approval / authorization escalation — **GAP, LIVE, FIXED**
Fixes applied (all compile-clean, all new tests green):
1. `pharmacy.py add_lot` (cross-tenant INSERT driven by client `business_id`/`item_id`) — now `assert_business_access` before insert. (Before: only `get_current_user`; live-mounted because `VERTICAL_PHARMACY` defaults True.)
2. `decisions.py apply_decision` (`UPDATE decision_log ... WHERE id=:id` with no business bound) — now requires `business_id` param, calls `assert_business_access`, and the UPDATE is bound `AND business_id = :business_id`. Cross-tenant apply now matches 0 rows. Added `test_apply_decision_requires_business_scoped_access`.
3. `finding_service.advance_status` / `verify_finding` (UPDATE by id, client-supplied `business_id` gated only at router) — now take a `business_id` and the SELECT/UPDATE are `AND business_id = :b`; router passes it. Finding status/verify can no longer advance another tenant's findings.
4. `upload.py stream_progress` (subscribed to `etl_progress:{upload_id}` with no ownership check) — now verifies upload ownership (same join used by `/status`/`/result`) before subscribing; otherwise 404.
5. `actions.py execute_action` (fetched `DecisionLog` by id only to build `previous_state`) — now scoped `DecisionLog.business_id == tenant.business_id`. Prevents leaking another tenant's decision item name/quantity.

Verified positives (no change needed): `money_audit.py` pattern (assert_business_access + assert_capability_for_business), `agent.py`, `orchestrator.py`, `intelligence.py` (42× `_verify_business_access`), `ops.py`/`admin_backup.py`/`partners.py` (platform-operator).

### J) Execution integrity — **PASS**
- `money_audit_service.py:863-914` status transitions `WHERE id AND business_id` + `VALID_TRANSITIONS`; `money_audit.py:407-421` requires `approved`; `action_executor.py:46-52` final execution_guard re-validation; `execution_guard.py:185-257` staleness/PO/reorder checks; `autonomy_service.py:243-244` re-verifies `pending_approval` before auto-execute.
- `actions.py` reverse/detail check `action.business_id != tenant.business_id`.

### K) Raw-SQL / RLS bypass — **PARTIAL (documented residual)**
- PASS: compute/update core is double-bound (`money_audit_service.py:67-95,199-269,864-905`; `audit_engine.py:157-162,240-241`; `execution_guard.py:228-233`; `etl_pipeline` inserts).
- PARTIAL: RLS-only id-scoped reads remain a defense-in-depth hole (all invoked behind an endpoint-level access gate, but no explicit business_id double-bind): `money_audit_service.py:743,771-781,819-846`; `money_audit.py:58-63,66-81,312-319,337-341`; `execution_guard.py:169-172` (cost-price read for cash-budget estimate).
- Intentional cross-tenant (by design, must remain permission/consent-gated): `recovery_match_service.py:256-286` (R2R matching joins all tenants), `recovery_match_matcher.py:52-60` (nightly scan). Flag for Item 11: `recovery_match_service.py:373-386 complete_match` UPDATE has **no party check** (unlike reveal/reject/report) — recommend gating on seller/buyer party in a follow-up.

### L) ETL grain & dedup — **PARTIAL (documented)**
- Item identity is name-only (`.strip().lower()`, no casefold/NFKC/SKU) (`etl_pipeline.py:285-286,327,372-375,484`) — real Duplicate-SKU/name-fragmentation finding (already carried to Items 8/11).
- `row_hash` (SHA-256 over business_id,item_id,location_id,source_tx_id,ts,qty,total) excludes `transaction_type`/`unit_price`/`cost_price`/`profit` — a legitimately distinct second line on same source/time/qty/total is silently dropped by `DO NOTHING` (`etl_pipeline.py:518-528,561`). Distinct SKUs can only share a hash after being merged to one item by the name-only upsert, so hash collisions across SKUs are blocked by `item_id` inside the hash.
- Inventory per-location conflict `(business_id,item_id,location_id)` is correct at head; the no-location duplicate guard is fail-closed (Item G fix).

### M) Migration / schema integrity — **PARTIAL (documented, no migration written)**
- PASS: `findings`, `decision_log`, `pharmacy_lots`, `chat_sessions` have RLS policies (`phase_b_rls_core_services.py:33-43`, `a25a714a2de8_add_tenant_rls_policies.py:30-42`).
- GAP: tenant-scoped `chat_messages` (free-text + `context_snapshot`) and `pos_sync_logs` (merchant `raw_response_sample`) have **no RLS policy** (`models.py:492-515,789-807`). Truly fixed only by a new migration that (a) adds RLS to those tables scoped to their FK chains and (b) grants to the app role. Pending—do not write migration this session (Item 11 recommendation).
- PARTIAL: historical `(business_id, row_hash)`-only partial index (`e6f8a0c2b4d6_add_transaction_dedup_row_hash.py:31-37`) was superseded by the correct 4-col index (`ff08_loc_grain_tenant_model.py:93-100`); ETL ON CONFLICT matches only the ff08 form — any DB stopped between the two migrations could absorb cross-location rows. Alea: verify migration chain lands on ff08 as head (Item 9 alembic check).

### N) Config / secrets hygiene — **PARTIAL (documented)**
- PASS: all secrets env-driven; `.env.example` is placeholders only; no committed key material in `app/` or tests (`tests/test_pii_redaction.py:15` is a fake); prod startup fails on default `SECRET_KEY` (`config.py:349-350`).
- GAP: `WHATSAPP_VERIFY_TOKEN` ships a real-looking code default `nazmos_ksa_whatsapp_2026` (`config.py:160`) with no prod fail-closed guard. Recommend removing the default or failing prod startup when unset. Documented, not changed (behavioral).

### O) CORS / auth token policy — **PARTIAL (documented)**
- PASS: CORS env-configured, no wildcard (`main.py:146-160`); access 60 min, refresh 30 days (`config.py:15-16`); login 5/5min, register 3/5min rate limits.
- PARTIAL: no logout/revocation/refresh-rotation; password policy `min_length=8` only (`schemas/auth.py:8`).

### P) Field-encryption breadth — **GAP (documented infra debt)**
- Only `users.two_factor_secret` uses `EncryptedText()` (`models.py:174`; `ff06_field_encryption`). Plaintext at rest: `users.password_hash/email/phone`, `team_invitations.token`, `notification_preferences.push_token`, `partners.bank_iban`, `businesses.cr_number/wasfaty_id`, `chat_messages.content/context_snapshot`, `decision_log.raw_output`. `pos_connections.credentials_encrypted` is pre-encrypted LargeBinary via vault (acceptable). Carry-forward to Item 11.

### Q) Redis/Celery tenant context — **PASS**
- Task payloads are opaque UUIDs only (`upload.py:242`, `event_engine.py:143`, `adapters.py:175`, `pos_sync_tasks.py:145-148`); per-task RLS re-set on both engines (`connection.py:16-25,47-73,110-132,158-176`); tasks open tenant context explicitly; supervisor tasks deliberately unscoped loops. No merchant data crosses the broker.

### R) Financial numeric discipline — **PASS**
- `Decimal`+`_money()` throughout money audit; all divisions guarded (`money_audit_service.py:115,180,126,129,301,471,519-521,532-533,894`). Coverage-aware velocity (`audit_core.coverage_aware_daily_velocity`) removes `<coverage>/30` from the canonical chain. Inventory of remaining `/30.0` (all safe/guarded): `recovery_match_service.py:132-133,265-266` (GREATEST+NULLIF), `intelligence_api.py:234`, `analytics_service.py:172,743,937,1115`, `inventory_orchestrator.py:46`, `nazm_planner.py:485`, `root_cause.py:36,95,219` (constant denom), `product_memory.py:257,539`, `branch_memory.py:119`, intelligence agents `GREATEST+NULLIF`. No div-by-zero found. Item 11: document these as secondary-chain (recovery-match/intelligence/planning only).

### S) Output gate / decision validation — **PASS** (2 notes)
- 16 fail-closed rules in `output_gate.py:109-241` incl. sig/freshness, size cap, strict JSON, financial-hallucination→error, injection→error, decision∈capsule, evidence_ids∈capsule, divergence-requires-challenge. Integration fail-closed: `opencode_brain.py:300-424` → deterministic fallback on gate rejection.
- Notes: `risk_flags` entries are warning-only (not allowlisted) (`ai_response_validator.py:255-261`); "challenge" accepts any reasoning containing the literal word (`output_gate.py:228`). Both advisory, not fail-open for execution.

### T) Webhook / POS — **PASS** (2 caveats)
- HMAC-SHA256 constant-time on raw body (`pos_webhooks.py:41-90`), shared-token fallback disabled in production; `resolve_webhook_business` requires active POSConnection, RLS set after positive resolution with teardown (`:93-131`). WhatsApp `receive_webhook` fails closed 503/401 when `WHATSAPP_APP_SECRET` unset (`whatsapp.py:52-59`).
- Caveats: replay protection is event-id dedupe only (`webhook_audit_service.py:33-42`), no timestamp/nonce window; `whatsapp.py:28-37` webhook verify uses the defaultable `WHATSAPP_VERIFY_TOKEN` (see N).

### U) Guest / public routes — **PARTIAL (health leak FIXED)**
- `guest_audit.py`: public but rate-limited 5/15min/IP, 10MB/5000-row caps, no tenant data — OK.
- `health.py /ready /health` previously leaked raw exception strings, `uploads_dir`, and env-var names publicly — **FIXED** this session: `_dependency_checks` now returns `"error"`/`"redis_unreachable"`/`"celery_unreachable"` constants, drops `uploads_dir`, keeps env-name list only; `/health/redis` and `/health/celery` scrub `reason` to constants.
- `/metrics` token-gated (`main.py:170-179`); `/pilot/status` benign.

### V) Error handling fail-closed — **PARTIAL (FIXED for public surface)**
- Global handler returns generic 500 (`main.py:333-341`). FIXED this session: `upload.py` four `detail=str(e)` leaks (storage retrieve/store, temporary file write, resolve-parse, `ingest-json`) → generic messages; exception detail still persists to `error_summary` column (tenant-scoped, internal) but never in HTTP body.
- Residual: `pos_webhooks.py:314` operator-only replay includes raw detail (operator surface, acceptable); `money_audit.py:248/271/295` controlled ValueError text (benign).

### W) Logging redaction & audit hygiene — **PARTIAL (documented)**
- Query strings stripped (`logger.py:180-198`, `logging_middleware.py:43,63`); `_PII_KEYS` + regex token/SA phone stripping; `security_audit_service._scrub_detail` is a strict allowlist (`:44-78`); `ai_reasoning_requests` persists fingerprints only.
- Residual: free-text merchant strings redacted only when matching keys/regex; `log_slow_query` emits raw SQL with inlined literals (`logger.py:286-292`).

### X) Idempotency & replay — **PARTIAL (documented)**
- `IdempotencyMiddleware` global but only for POST/PATCH/PUT with `Idempotency-Key`; client-driven, not enforced server-side (`idempotency.py:25-90`). POS webhooks event-id dedupe + learning/goal `ON CONFLICT` upserts (`outcome_learning.py:105-119`).

### Y) Dead code / experiment sprawl / docs-vs-code truth — **PARTIAL (documented)**
- `USE_CELERY/USE_REDIS/USE_CLIENT_ETL` default False (`config.py:26-28`) — operational infra opt-in (documented). `execution_engine.execute_job` honestly sets `"simulated": True` (`execution_engine.py:92`) — matches its docstring, no doc lie. Real local executor exists separately with guards.
- Sprawl: `scripts/v9..v12` + `sample_data/v9..v12` in-tree; duplicated financial measures `money_audits.money_at_risk_sar` vs `capital_at_risk_sar` (`models.py:1404-1406`) written from the same value (`money_audit_service.py:559-561`), legacy alias retained for API compat.

---

## Router dependency table (Item 7 evidence)

Authn legend: `u` = `get_current_user`; `tc` = tenant_context / capability.

| Router | Authn | Access check | Capability | Notes |
|--------|-------|--------------|------------|-------|
| health | none | n/a | n/a | FIXED: no raw exc / dir leak |
| auth | n/a | n/a | n/a | register/login/refresh/me/demo; no logout/rotation |
| guest_audit | none | n/a | n/a | rate-limited, capped, no tenant data |
| businesses | u | self-scoped | – | bootstrap self only |
| dashboard | u | assert | – | |
| inventory | u | assert | – | restock gated |
| upload | u | assert (POST/history/ingest) | – | FIXED: progress ownership |
| money_audit | u | assert + capability | can_approve_actions | strongest pattern (reference) |
| decisions | u | assert (recommend/apply now) | – | FIXED: apply business-bound |
| audits | u | assert | – | FIXED: finding status/verify business-bound |
| forecast | u | assert | – | |
| intelligence | u | `_verify_business_access` (42×) | – | consistent |
| ops | u | platform-operator | is_platform_operator | |
| compliance | u | owner | – | |
| events | u | `_verify_business_access` | – | |
| orchestrator | u | assert + capability + feature | owner/admin/manager | |
| pilot | u | assert (recommendations); /status public | – | |
| pos_webhooks | HMAC | resolve_webhook_business | – | RLS after resolve |
| recovery_match | u | assert + capability + feature | | |
| agent | u | assert + capability + feature | owner/admin | |
| pharmacy | u | assert (list); FIXED add_lot | – | GAP closed |
| whatsapp | HMAC | webhook HMAC; test-approve u-only | – | test-approve non-prod only |
| suppliers | u | – (global demo list) | – | read-only |
| partners | u | platform-operator | | |
| admin_backup | u | platform-operator | | |
| oauth | u / public callback | authorize asserts | | |
| chat | u | assert on POST `/`; sessions/suggestions/reason: none | | GAP if CHAT_ENABLED (latent, default off) |
| actions | tc | capability via tenant_context; FIXED execute scope | can_approve_actions | only if BILLING_ENABLED (default off) |
| organizations / subscriptions / adapters | tc | context-validated | | only if BILLING_ENABLED (default off) |

Latent (feature-flagged, currently unmounted in default KSA config): chat, actions, organizations, subscriptions, adapters. Defaults: `CHAT_ENABLED` off, `BILLING_ENABLED` off, `VERTICAL_PHARMACY` on (hence pharmacy fix was live-critical).

---

## What changed this session (Item 7 fixes — no commit yet)

Files edited (all `python -m compileall` clean):
- `app/routers/pharmacy.py` — `add_lot` asserts business access.
- `app/routers/decisions.py` — `apply_decision` takes `business_id`, asserts access, UPDATE bound to business.
- `app/services/finding_service.py` — `advance_status`/`verify_finding` accept `business_id` and bind SELECT/UPDATE.
- `app/routers/audits.py` — passes `business_id` into both service calls.
- `app/routers/upload.py` — `stream_progress` ownership check; four `detail=str(e)` leaks turned into generic messages.
- `app/routers/health.py` — `_dependency_checks` returns error constants (no raw exception text, no `uploads_dir`); `/health/redis`, `/health/celery` scrub `reason`/`error`.
- `app/routers/actions.py` — `execute_action` DecisionLog lookup scoped to tenant.

Tests added:
- `tests/test_decisions.py` — `test_apply_decision` now passes `business_id`; new `test_apply_decision_requires_business_scoped_access`.
- `tests/regression/test_adversarial_matrix.py` — `TestISecondAuditTenantScopedWritesAndNoRawLeaks` (9 DB-free source-level guards).

## Escalation to Items 8 / 9 / 11
- Item 8 (root-cause assertions) will cite: 6-days-never-30 (now coverage-aware everywhere in canonical chain), location-collapse fail-closed (G), UNKNOWN→0 (F), plus the new tenant-scope fixes as the I-dimension assertion.
- Item 9 (full run) must record the pre-existing `test_etl_dedup.py` SQLite ON-CONFLICT failures, the pre-existing event-loop teardown flake in `test_celery_rls_tenant_context.py` under large combined runs (passes in isolation on a migrated test DB), and any RLS/limiter DB-gated errors — without hiding them.
- Item 11 residual list grows with: `chat_messages`/`pos_sync_logs` RLS; `WHATSAPP_VERIFY_TOKEN` default; field-encryption breadth; `recovery_match_service.complete_match` party check; `money_at_risk_sar` legacy alias; v9-v12 sprawl.