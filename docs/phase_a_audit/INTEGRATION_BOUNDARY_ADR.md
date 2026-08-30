# ADR: Integration Boundary Verification (Backends + HTTP)

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

Three external integrations are **partially implemented** with webhook receivers but **no live credentials** configured. All run in **mock/fallback mode** in development. Production readiness is **NOT VERIFIED**.

---

## 2. Integration Surface Map

| Integration | Protocol | Webhook Router | Adapter | Credential Status | Mock Mode |
|-------------|----------|----------------|---------|-------------------|-----------|
| **Foodics** | HMAC-SHA256 webhook | `/api/v1/pos/webhook` (pos_webhooks.py) | `app/adapters/foodics.py` | `FOODICS_WEBHOOK_SECRET` = "" | ✅ No secret → 401 |
| **Salla** | HMAC-SHA256 webhook | `/api/v1/pos/webhook` (pos_webhooks.py) | `app/adapters/salla.py` | `SALLA_WEBHOOK_SECRET` = "" | ✅ No secret → 401 |
| **WhatsApp Business Cloud** | HMAC-SHA256 webhook + Graph API | `/api/v1/whatsapp/webhook` (whatsapp.py) | `app/services/whatsapp_bridge.py` | `WHATSAPP_APP_SECRET` = "", `WHATSAPP_TOKEN` = "" | ✅ `WHATSAPP_ENABLED=mock` |

---

## 3. Boundary Verification

### 3.1 Foodics + Salla (POS Webhooks)

**Router**: `app/routers/pos_webhooks.py`  
**Auth**: `verify_pos_webhook_auth()` — HMAC-SHA256 signature verification

| Provider | Header | Secret Setting | Behavior if Missing |
|----------|--------|----------------|---------------------|
| Foodics | `x-foodics-signature` | `FOODICS_WEBHOOK_SECRET` | 401: "not configured; cannot verify" |
| Salla | `x-salla-signature` | `SALLA_WEBHOOK_SECRET` | 401: "not configured; cannot verify" |
| Fallback | `x-webhook-token` | `FOODICS_WEBHOOK_TOKEN` / `SALLA_WEBHOOK_TOKEN` | Dev only; 401 in production |

**Adapters**: `app/adapters/foodics.py`, `app/adapters/salla.py`  
- Idempotency: `SELECT ... WHERE reference_id = :ref` (dedup on order ref)
- Inventory deduction: `UPDATE inventory SET current_stock = GREATEST(0, current_stock - :q)`
- Transaction ledger: `INSERT INTO transactions ...`
- Item resolution: `app/adapters/item_resolver.py` (fuzzy match by name/SKU/barcode)

**Webhook Audit**: `app/services/webhook_audit_service.py` records every inbound event to `WebhookEvent` table with payload hash, signature validity, status.

**Status**: ✅ **Boundary enforced** — no secret = 401. No live credentials = cannot receive real webhooks.

---

### 3.2 WhatsApp Business Cloud

**Router**: `app/routers/whatsapp.py`  
**Auth**: `x-hub-signature-256` HMAC via `WHATSAPP_APP_SECRET`

| Mode | `WHATSAPP_ENABLED` | Behavior |
|------|-------------------|----------|
| `mock` | Logs to console, returns deep-link fallbacks | Default dev |
| `live` | Requires `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` | Production |

**Bridge**: `app/services/whatsapp_bridge.py`
- `send_notification(to, template, params)` — template-based messaging
- `send_approval_request(action_id, ...)` — interactive buttons (Approve/Reject)
- Mock mode: prints to log, returns `{"status": "mock_sent", "deep_link": "..."}`

**Interactive Flow** (whatsapp.py webhook):
- Inbound button replies: `approve_price_shield_<action_id>` / `reject_price_shield_<action_id>`
- Calls `agent_action_executor.approve_agent_action()` / `reject_agent_action()`

**Status**: ✅ **Boundary enforced** — no `WHATSAPP_APP_SECRET` = 503. Mock mode = no live calls.

---

### 3.3 OAuth Connections (Salla / Foodics)

**Module**: `app/services/oauth_manager.py`  
**Endpoints**: `app/routers/oauth.py` (not fully traced)

| Provider | Auth URL | Token URL | Scope |
|----------|----------|-----------|-------|
| Salla | `accounts.salla.sa/oauth2/auth` | `accounts.salla.sa/oauth2/token` | `orders.read, products.read` |
| Foodics | `console.foodics.com/oauth/authorize` | `console.foodics.com/oauth/token` | `orders.read, inventory.read` |

**Credential Storage**: `app/services/credential_vault.py` — encrypted with `CREDENTIAL_MASTER_KEY`.

**Status**: ⚠️ **OAuth flow not end-to-end tested** — no live client credentials.

---

## 4. HTTP Client Patterns

| Module | Client | Usage |
|--------|--------|-------|
| `whatsapp_bridge.py` | `httpx.AsyncClient` | Graph API POST |
| `llm_orchestrator.py` | `httpx.AsyncClient` | Groq/Google API |
| `oauth_manager.py` | `httpx.AsyncClient` | Token exchange |
| `schema_detector.py` | None | CSV parsing only |

**No shared HTTP client** — each module creates its own `AsyncClient`. Consider centralizing for connection pooling / timeouts / retries.

---

## 5. Verification Status

| Integration | Webhook Receiver | Adapter | Credentials | Live Tested |
|-------------|-----------------|---------|-------------|-------------|
| Foodics | ✅ HMAC verified | ✅ Idempotent + inventory | ❌ Empty secrets | ❌ NO |
| Salla | ✅ HMAC verified | ✅ Idempotent + inventory | ❌ Empty secrets | ❌ NO |
| WhatsApp | ✅ HMAC verified | ✅ Mock bridge + approvals | ❌ Empty secrets | ❌ NO |
| OAuth (Salla/Foodics) | ⚠️ Router exists | ⚠️ Manager exists | ❌ No client IDs | ❌ NO |

---

## 6. Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Webhook signature verification bypassed | Low | `hmac.compare_digest` used; missing secret = 401/503 |
| Duplicate order processing | Low | Idempotency key = `reference_id` on `transactions` table |
| WhatsApp approval spoofing | Low | HMAC + action_id in button payload |
| OAuth token leakage | Medium | `CREDENTIAL_MASTER_KEY` encrypts at rest |
| No rate limiting on webhooks | Medium | Add per-IP / per-business limits |

---

## 7. Conclusion

**All integration boundaries are correctly enforced** — missing credentials = explicit 401/503, not silent failure. However, **no integration is production-verified** without live credentials. Mock modes provide $0 development but do not validate real API contracts.

**Recommendation**: Before production, run contract tests against sandbox environments with real credentials.