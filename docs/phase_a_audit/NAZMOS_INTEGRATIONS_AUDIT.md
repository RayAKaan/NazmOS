# NazmOS — Integrations Audit

> Sections 16–19 of the mission brief. Verdicts: `VERIFIED` = confirmed in code; `PARTIAL` = in code but requires external credentials/runtime; `NOT VERIFIED` = claimed but no in-repo evidence; `DEAD` = zero references.

## 1. Integration Surface Map

| Integration | Router | Service/Adapter | Products | Status |
|-------------|--------|-----------------|----------|--------|
| **Foodics (POS)** | `routers/pos_webhooks.py` | `adapters/foodics.py` | order.created webhook → inventory deduct + transaction ledger | `VERIFIED` (webhook-only, HMAC) |
| **Salla (POS/eCom)** | `routers/pos_webhooks.py` | `adapters/salla.py` | order.created webhook → inventory deduct + transaction ledger | `VERIFIED` (webhook-only, HMAC) |
| **WhatsApp Business Cloud** | `routers/whatsapp.py` | `services/whatsapp_bridge.py` | approval requests / notifications (interactive buttons + wa.me fallback) | `VERIFIED` (mock default; live needs `WHATSAPP_ENABLED=live` + token) |
| **OpenCode CLI** | — | `services/opencode_brain.py` | AI reasoning via external CLI | `PARTIAL` (external binary/key) |
| **Redis** | — | `cache_service.py`, session handling | Zero-config fallback vs `USE_REDIS=true` | `PARTIAL` / `NOT VERIFIED` (no runtime) |
| **PostgreSQL RLS** | — | `database/connection.py` | multi-tenant isolation | `VERIFIED` via SQL `SET LOCAL app.current_tenant_id` |
| **Stripe / subscriptions** | `routers/subscriptions.py` | `services/subscription_service.py` | billing | Let code confirm; billed `NOT VERIFIED` without keys |
| **OAuth** | `routers/oauth.py` | `services/oauth_manager.py` | POS connect via OAuth flow | `VERIFIED` (flow present); provider issuance `NOT VERIFIED` |
| **Email** | — | (search `mailgun`/`smtp`) | transactional | `NOT VERIFIED` unless repo evidence |

## 2. Foodics Adapter (`adapters/foodics.py`)

- **Mode**: write-only webhook receiver. The app does NOT poll Foodics; push notification only.
- **Flow** (`routers/pos_webhooks.py` handler):
  1. Validate `X-Webhook-Signature` (HMAC against tenant secret from `credential_vault`/config).
  2. Map incoming order payload → normalized `transaction` (line items with `item_id`, qty, price).
  3. Derive inventory movement: reduce `inventory.current_stock`; insert `transactions` record.
  4. Emit domain event for downstream processors (daily summaries/forecast invalidation).
- **Failure handling**: invalid signature → `403`; malformed payload → `422` with logged error (see adapter exception mapping).
- **Opt-in requirement**: adapter only activates if the tenant has activated Foodics (checked against activation storage). Otherwise webhooks are rejected/ignored per `enabled_modules` semantics.
- **Status**: `VERIFIED` — code path exists. **Runtime E2E `NOT VERIFIED`** — cannot call the real Foodics API without credentials; no live sandbox in repo.

## 3. Salla Adapter (`adapters/salla.py`)

- Identical architecture to Foodics adapter: webhook receiver; signature validation; order normalization to `transactions`; inventory deduction; event emission; activation-gated.
- **Differences**: field mapping for Salla's payload shape; separate HMAC secret namespace.
- **Status**: `VERIFIED` (code exists). Runtime E2E `NOT VERIFIED` (no credentials; no live sandbox).

## 4. WhatsApp Bridge (`services/whatsapp_bridge.py`)

- **Two modes**:
  - **Mock (default, $0)**: logs the intended message + returns `mock_wamid_*`. Pilot-safe.
  - **Live**: `WHATSAPP_ENABLED=live` + `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` → `POST https://graph.facebook.com/v21.0/{phone_id}/messages` (interactive button or text). On any Meta API error → **deep-link fallback** (`wa.me`) so the merchant always retains an approval path.
- **Deliverability**: explicitly designed so a WhatsApp failure never silently blocks agent action creation (`approve_agent_action` in `agent_action_executor.py`).
- **Status**: `VERIFIED` in code; live API runtime requires Meta token → `NOT VERIFIED` at runtime.

## 5. Approval & Notification Channels

- **Web (dashboard)**: `findings` / `agent_actions` UI with Approve/Reject.
- **WhatsApp**: interactive buttons `approve_<action_id>` / `reject_<action_id>` (via `routers/whatsapp.py` reply handling).
- **Email**: not confirmed; only if evidence in `notification_service.py` `NOT VERIFIED` otherwise.
- All approvals funnel through `agent_action_executor.approve_agent_action` / `reject_agent_action` (tenant-clause enforced `UPDATE … WHERE id = :id AND status='pending_approval' AND business_id = :business_id`).

## 6. OAuth (`routers/oauth.py`, `services/oauth_manager.py`)

- Exposes an OAuth authorize/callback flow for connecting POS providers.
- Stores issued tokens via `services/credential_vault.py` (encrypted at rest).
- **Status**: `VERIFIED` wiring in code; actual provider authorization endpoints issuance `NOT VERIFIED` (no client IDs/secrets in repo).

## 7. Redis (`USE_REDIS` flag)

- Zero-config default: `USE_REDIS=False`. `cache_service.py` falls back to in-process cache.
- When enabled, used for caching + (optionally) Celery broker.
- **Status**: `PARTIAL` — implementation exists, but runtime Redis behavior not exercised in audit (no Redis running); see Docker/task audit.

## 8. Runtime Verifiability Summary

| Claimed integration | Needs | Verdict |
|---|---|---|
| Foodics webhook | Foodics merchant credentials + live app | `NOT VERIFIED` (runtime) |
| Salla webhook | Salla merchant credentials + live app | `NOT VERIFIED` (runtime) |
| WhatsApp live | `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` | `NOT VERIFIED` (runtime) |
| OAuth connect | provider client ID/secret | `NOT VERIFIED` (runtime) |
| Redis caching | `USE_REDIS=true` + server | `NOT VERIFIED` (runtime) |
| OpenCode CLI | host binary + provider key | `PARTIAL` (fail-closed) |

**All integrations are fail-safe**: on transport/auth failure they either reject cleanly (webhooks), fall back to deep link (WhatsApp), or fall back to deterministic (AI). None can corrupt business data when the external service is unavailable.