# NazmOS — Access Control Model

Canonical reference for how authorization works across the NazmOS backend and
frontend, including the capability schema, the endpoint audit table, route
visibility, enforcement layers, and the hardening-track test coverage.

---

## 1. Capability schema

Single source of truth: `backend/app/services/capabilities_service.py`.
Six boolean capabilities plus a resolved business `role`. Split into platform
(operator-owned) and business (tenant-owned) capabilities.

| Capability                | Kind     | Resolved when                                             | Guards |
|---------------------------|----------|-----------------------------------------------------------|--------|
| `is_platform_operator`    | platform | DB `is_platform_operator` flag OR email in `FOUNDER_EMAILS` allowlist | operator checks, `/auth/me` |
| `can_view_ops_console`    | platform | operator                                                   | `/ops` page (frontend) |
| `can_run_admin_tools`     | platform | operator                                                   | admin backups, partner approvals, POS webhook replay, nightly scans |
| `can_manage_team`         | business | role `owner` \| `admin`                                   | team invite/update/remove |
| `can_run_orchestrator`    | business | role `owner` \| `admin` \| `manager`                      | orchestrator rebalance / profit-scan |
| `can_approve_actions`     | business | role `owner` \| `admin`                                   | agent + money-audit actions |

### Role resolution rules

- A caller with **no relationship** to the business resolves to `role = None`
  and every business capability is `false` — even if a `business_id` is supplied.
- Business capabilities are always evaluated in the caller's **active business
  context** (`_resolve_business_role`); the platform capabilities are global.
- The object carries `role` and resolved `business_id`; `_all` is internal and
  never serialized. `Capabilities.has(capability)` and `to_dict()` back both
  server-side `require_capability` and the `/auth/me` response.

Serialized shape returned by `login`, `register`, and `/auth/me`:

```json
{
  "is_platform_operator": false,
  "can_view_ops_console": false,
  "can_run_admin_tools": false,
  "can_manage_team": true,
  "can_run_orchestrator": true,
  "can_approve_actions": true,
  "role": "owner",
  "business_id": "5f0a1e10-..."
}
```

---

## 2. Enforcement layers

| Layer | Mechanism | What it blocks |
|-------|-----------|----------------|
| App-level capability gate | `assert_platform_operator` (`middleware/business_access.py`), `require_capability(cap, business_id)` (`middleware/rbac.py`), `assert_business_access` | Authorization decisions: tenant mismatch, role/capability shortfall |
| Row-Level Security (RLS) | `SET LOCAL app.current_tenant_id` per request (`database/connection.py`, `middleware/rls_tenant.py`); RLS enabled on tenant tables + intelligence/recovery tables (migration `b7c8d9e0f1a2`) | Defensive depth: accidental cross-tenant rows even if an app-level gate is missed |
| Denial audit trail | `record_access_denial` (`services/audit_log_service.py`) writes `audit_log` rows with `action_category = "authorization"` | Visibility: every denied access is attributable (subject tenant, actor, reason) |
| Frontend route gate | `RouteGuard` + `middleware.ts` | UX-level: unauthenticated → `/login`; capability shortfall → `/dashboard` |

> Important: the RLS tenant context is derived from the **client-supplied**
> `business_id`, so RLS alone cannot be trusted to stop a cross-tenant read.
> The app-level `assert_business_access` is the authoritative gate; RLS is
> defense-in-depth for writes.

---

## 3. Backend endpoint audit table

Legend — scope: `P` platform (operator only), `B` business (tenant-scoped),
`N` none/public.

### Platform-gated (operator only)

| Method | Path | Gate |
|--------|------|------|
| GET  | `/api/v1/ops/pilot-console` | `assert_platform_operator` |
| POST | `/api/v1/admin/backups` (create) | `assert_platform_operator` |
| GET  | `/api/v1/admin/backups` (list) | `assert_platform_operator` |
| GET  | `/api/v1/admin/backups/{filename}` (download) | `assert_platform_operator` |
| POST | `/api/v1/admin/backups/{filename}/restore-dry-run` | `assert_platform_operator` |
| POST | `/api/v1/admin/backups/retention` | `assert_platform_operator` |
| POST | `/api/v1/pos/admin/webhooks/{event_id}/replay` | `assert_platform_operator` (replaced dead `require_role("admin","owner")`) |
| POST | `/api/v1/partners/admin/{partner_id}/approve` | `assert_platform_operator` |

### Capability-gated (business context)

| Method | Path | Capability |
|--------|------|------------|
| GET | `/api/v1/orchestrator/rebalance` | `can_run_orchestrator` (business_id) |
| GET | `/api/v1/orchestrator/profit-scan` | `can_run_orchestrator` (business_id) |

### Business-scoped (tenant access asserted)

| Method | Path | Gate |
|--------|------|------|
| POST | `/api/v1/chat/` | `assert_business_access` |
| GET  | `/api/v1/pharmacy/lots` | `assert_business_access` |
| GET  | `/api/v1/decisions/recommend` | `assert_business_access` |
| GET  | `/api/v1/dashboard/summary` | `assert_business_access` |
| GET  | `/api/v1/inventory` | `assert_business_access` |
| GET  | `/api/v1/money-audit/current` | `assert_business_access` |
| GET  | `/api/v1/recovery/settings` | `assert_business_access` |
| GET  | `/api/v1/events` | `assert_business_access` |
| GET  | `/api/v1/intelligence/memory/current-state` | `assert_business_access` |
| GET  | `/api/v1/intelligence/context` | `assert_business_access` |
| GET  | `/api/v1/forecast/all` | `assert_business_access` |
| * | `/api/v1/actions/*`, `/api/v1/adapters/*`, `/api/v1/organizations/*`, `/api/v1/subscriptions/*`, `/api/v1/teams/*` | tenant-context path (existing) |

### Public / unauthenticated (intentional)

- `POST /api/v1/pos/foodics/webhook`, `POST /api/v1/pos/salla/webhook` — external POS provider callbacks (signature-checked upstream).
- `/api/v1/partners/apply`, `/api/v1/partners/public`, `/api/v1/partners/me`, `/api/v1/partners/dashboard`, `/api/v1/partners/referrals*` — self-service partner surface. `list_active_partners` projects only `id, partner_type, name, city, commission_pct, total_converted` (no PII/financials).
- `guest_audit`, `health`, auth, shariah endpoints.

### Notes

- Prior dead gates (`require_role("admin", ...)`) were removed — no such roles
  exist, so those checks were no-ops. They are replaced by
  `assert_platform_operator` (real enforcement).
- `assert_business_access` returns **403** for a known tenant you don't belong
  to and **404** for an unknown tenant (no existence oracle).
- Partner listing no longer leaks `referral_code`, `bank_iban`, revenue, email,
  or phone.

---

## 4. Frontend route visibility

| Route | Guard | Behavior |
|-------|-------|----------|
| `/login`, `/register` | `middleware.ts` | authenticated user → redirect `/dashboard` |
| all dashboard routes | `middleware.ts` | unauthenticated → redirect `/login` |
| `/api/*` | `middleware.ts` | inject `Authorization: Bearer <token>` from `nazm_access` cookie |
| `/ops` | `RouteGuard require="can_view_ops_console"` | non-operator → redirect `/dashboard` |

- `frontend/src/lib/auth.ts` — `Capabilities`, `hasCapability()`, typed `MeResponse`.
- `frontend/src/stores/authStore.ts` — capabilities persisted on login/register/demo/`checkAuth`.
- `frontend/src/components/RouteGuard.tsx` — reusable client-side gate (auth + capability).

---

## 5. Hardening-track coverage

- `backend/tests/security/test_idor_cross_tenant.py` — **21 tests** (19 cross-tenant
  IDOR/positive/not-found cases + 2 denial-audit cases), all passing:
  an attacker cannot read another tenant's data across 11 endpoints; owner
  positive controls pass; unknown business → 404; merchants get 403 on
  operator-only endpoints; denials are written to `audit_log`.
- `frontend/src/components/RouteGuard.test.tsx` + `frontend/src/middleware.test.ts`
  — **9 Jest tests**, run in CI via `npm test -- --ci --runInBand`.
- Denial-logging proof: `record_access_denial` writes `action_category="authorization"`
  rows (`access_denied_tenant_access`, `access_denied_is_platform_operator`) with
  reasons such as `not_owner_or_team_member`, `not_platform_operator`,
  `business_not_found`.

### Design tokens (UI consolidation)

`frontend/tailwind.config.ts` now defines `brand.*`, `navy.*`, `whatsapp.*`,
`chat.*`, `status.*`, `text.*`, `bg.*` groups. Ad-hoc Tailwind color literals
were consolidated: **612 → 0** hex colors in class attributes across `src`
(43 remain only as legitimately dynamic inline `style` values). Shared
`Button`, `Card`, `Badge`, `Input`, `Toast` components live in
`src/components/ui/`.
