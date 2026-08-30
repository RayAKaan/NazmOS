# FRONTEND_PAGE_MAP

Audited against the **live `next build` route list** (26 pages, `scripts/check_frontend_routes.mjs`) and the **server-side auth guards** in `src/middleware.ts`. Every claim below is backed by script output, not by eyeballing.

Scripts:
- `scripts/check_frontend_routes.mjs` — route/link integrity (PASS, 0 live-broken)
- `scripts/check_a11y.mjs` — axe-core scan over 28 built pages (PASS, 0 serious violations)

---

## Route inventory

Legend — Auth: `PUB` public · `MID` protected server-side by middleware · `CLIENT` protected client-side via `(dashboard)/layout.tsx` redirect (not in middleware matcher). Orphan: page never linked from live code (reached by typed URL / external link / PWA).

| Route | Purpose | Reached via | API endpoints on load | Auth | Feature flags | Orphan |
|---|---|---|---|---|---|---|
| `/` | Marketing landing (inline nav, demo embed, pricing) | brand/SEO | none | PUB | none | no |
| `/demo` | Permanent redirect → `/product-demo` (301, `permanentRedirect`) | Header legacy, landing dead code | none | PUB | none | no |
| `/product-demo` | Interactive Money Audit simulator (10-step stepper) | nav, `/demo` | none (mock data) | PUB | none | no |
| `/login` | Auth sign-in | middleware redirect, nav | `POST /api/v1/auth/login` | PUB | none | no |
| `/register` | Auth sign-up (intent-aware: free-audit) | nav, `/product-demo` CTA | `POST /api/v1/auth/register` | PUB | none | no |
| `/onboarding` | 4-step zero-API onboarding wizard | post-register | none | CLIENT | none | no |
| `/mobile` | Standalone PWA shell (mobile-first feed) | device home screen | `GET /api/v1/agent/feed` | CLIENT | none | YES (justified) |
| `/partners` | External partner signup form | partner emails | `POST /api/v1/partners/...` | PUB | none | YES (justified) |
| `/terms` | Terms (incl. pilot-support policy) | footer | none | PUB | none | no |
| `/privacy` | Privacy policy | footer | none | PUB | none | no |
| `/dashboard` | Money Audit summary + intelligence cards | sidebar Home | `GET /api/v1/money-audit/current`, agent feed | MID | — | no |
| `/feed` | Nazm attention feed (approve/reject) | sidebar | `GET /api/v1/agent/feed` | MID | `NEXT_PUBLIC_AGENT_ENABLED` | no |
| `/chat` | Nazm Copilot (unified intelligence chat) | sidebar | chat API | CLIENT | `NEXT_PUBLIC_AGENT_ENABLED` | no |
| `/orchestrator` | Recovery Engine orchestrator | sidebar | orchestrator API | MID | `NEXT_PUBLIC_AGENT_ENABLED` | no |
| `/money-audit` | Free Money Audit (recovery actions, WhatsApp) | sidebar, first-run CTA | `GET /api/v1/money-audit/current`, `POST .../generate`, action approve/reject/complete | MID | none | no |
| `/recovery-match` | Recovery Match (surplus listings, match engine) | sidebar | recovery-match API | MID | `NEXT_PUBLIC_AGENT_ENABLED` | no |
| `/upload` | File upload + column mapping | sidebar, empty-state CTAs | upload endpoints | MID | none | no |
| `/inventory` | Stock table, filters, reorder modal | sidebar | `GET /api/v1/inventory/...` | CLIENT | `NEXT_PUBLIC_VERTICAL_PHARMACY` | no |
| `/inventory/expiry` | Pharmacy expiry lots + SFDA recall | sidebar Tools | expiry API | CLIENT | `NEXT_PUBLIC_VERTICAL_PHARMACY` | no |
| `/forecast` | Demand Forecast (Prophet, KSA) — **built this audit** | sidebar | `GET /api/v1/forecast/cache`, `/summary`, `/forecast/{id}`, `POST /forecast/` | CLIENT | none | no |
| `/integrations` | POS webhooks | sidebar | integrations API | MID | none | no |
| `/ops` | Founder pilot console | sidebar | `GET /api/v1/ops/pilot-console` | MID | none | no |
| `/team` | Team members + invitations | sidebar | `GET/POST/PATCH /api/v1/organizations/team...` | MID | none | YES (justified) |
| `/suppliers` | Supplier network (mock-seeded) | sidebar Tools | none yet (TODO: `GET /api/v1/suppliers`) | CLIENT | none | no |
| `/chain` | Multi-branch chain dashboard | typed URL only | chain API | MID | none | YES (justified) |
| `/settings/autonomy` | Autonomy dial + settings | sidebar | settings API | MID | none | no |

Route source: `scripts/check_frontend_routes.mjs` → `ROUTES (26)` list. Auth column from `src/middleware.ts:4-16` (`PROTECTED_SEGMENTS`) + `(dashboard)/layout.tsx` client guard. Orphan status from checker `ORPHANED PAGES (4)` block.

---

## Confirmed findings and fixes (with proof)

### 1. `/forecast` — every sidebar click 404'd
- **Proof:** baseline run `BROKEN LINKS — LIVE CODE (1): /forecast (Sidebar.tsx:24)` → exit 1.
- **Fix:** built `src/app/(dashboard)/forecast/page.tsx` (Prophet summary + cached-item list + 7-day curve + refresh, LoadingState/EmptyState wired). Rebuild → checker now `ROUTES (26)` includes `/forecast`, 0 live-broken.
- **Decision:** **build the page** (not remove nav) — backend router `forecast.py` + `types/forecast.ts` were already present.

### 2. Header marketing links → broken `/pricing`, `/industries/*`
- **Proof:** baseline `BROKEN LINKS — LIVE CODE: /pricing + /industries/{supermart,cafe,retail,hotel} (Header.tsx:97-103)`.
- **Fix:** converted `Header.tsx` to a dashboard top bar (brand → `/dashboard`, demo → `/product-demo`, CTA → `/upload`, mobile menu with `aria-label`). All 5 links removed; landing keeps its own inline nav.

### 3. `/chain` dead links
- **Proof:** baseline `BROKEN LINKS — LIVE CODE: /organizations/settings (chain/page.tsx:106)` plus dynamic `/chain/{id}` rows with no `[id]` route.
- **Fix:** Settings button → static "coming soon" span; location rows de-Linked (no detail page exists). Unused `Link`/`ChevronRight` imports removed.

### 4. `/demo` vs `/product-demo` duplication
- **Proof:** `demo/page.tsx:11` used `redirect()` (HTTP 307).
- **Fix:** `permanentRedirect("/product-demo")` → HTTP 301. Route kept so `/demo` links resolve (checker stays green) while canonicalizing to `/product-demo`. Header no longer ships a duplicate "Demo" link.

### 5. Bootstrap race → duplicate businesses
- **Proof:** `(dashboard)/layout.tsx:22-39` fired `POST /businesses/bootstrap` with no in-flight lock (StrictMode double-invoke); backend `businesses.py` was select-then-insert with no unique constraint.
- **Fix (both, per decision):**
  - Frontend: `useRef` in-flight lock guards concurrent calls.
  - Backend: partial unique index `uq_businesses_active_owner (owner_id WHERE is_active = true)` + `INSERT ... ON CONFLICT DO NOTHING` then re-select. Migration `5f0a1b2c3d4e` deactivates legacy duplicates (keeps oldest). Verified: router + model import clean in running container.

### 6. Mobile nav parity
- **Proof:** `MobileNav.tsx` had 5 items vs Sidebar 11+ (feed, chat, orchestrator, forecast, integrations, ops, expiry, suppliers, settings missing).
- **Fix:** MobileNav now = 5 primary + bottom-sheet "More" menu mirroring all Sidebar items + settings. i18n keys added (`sidebar.more`, `sidebar.allTools`, `sidebar.close` in en/ar).

### 7. Loading states
- **Proof:** no shared loading primitive; ~17 bespoke sites (Skeleton, animate-pulse divs, text placeholders).
- **Fix:** created `components/ui/LoadingState.tsx` (variants: spinner/cards/table/chart, `role="status"`). Adopted in new `/forecast`. Existing pages left as-is (in-scope for the audit deliverable only).

### 8. Empty states
- **Proof:** 6/6 list pages lacked a next-action CTA at audit start.
- **Fix:** created `components/ui/EmptyState.tsx` (icon/title/description/actions). Applied to: `/forecast`, `/suppliers`, `InventoryTable` (all → "Upload files" CTA). Money Audit already had a strong empty state; Feed's "All clear" is intentionally CTA-free.

### 9. Error states
- **Proof:** 0 `error.tsx` files; `ops/page.tsx:53` and `money-audit/page.tsx:210` rendered raw `detail` (could be a FastAPI validation array → `[object Object]`).
- **Fix:** shared `errorMessage()` in `lib/utils.ts` (coerces string/array detail, filters "Network Error"); applied in ops + money-audit. Added root `error.tsx` + `(dashboard)/error.tsx` client error boundaries.

### 10. RTL / Arabic
- **Proof:** root `html` hardcoded `dir="ltr"` (`layout.tsx:62`); i18n only patched `documentElement.dir` post-hydration (FOUC).
- **Fix:** pre-paint inline script in `<head>` reads `nazmos-locale` and sets `dir`/`lang` before render; `I18nProvider` writes a same-value cookie (SSR/refresh parity). Layout shell converted to logical properties (`start-0`, `ms-auto`, `ms-60`, `border-e` in Sidebar/MobileNav/dashboard layout).

### 11. Mobile parity (navigation)
- Covered by #6. Checker now counts MobileNav + Header + Sidebar links; any new mismatch fails CI.

### 12. Design tokens
- **Measurement:** 614 hex-color usages and 956 arbitrary-value utilities in `src` (audit measurement). Token source of truth remains `tailwind.config.ts` + `globals.css` (`--bg-*`, `--text-*`, `--accent-*`, `--border-*`, `--status-*`).
- **Decision (this audit):** documented only, **no blind mass-replace** — 500+ arbitrary hexes are a high-regression-risk, low-value change; recommended as a follow-up with a codemod + visual regression gate.

### 13. Badges
- **Measurement:** 9 `badge:` usages, all in `Sidebar.tsx`. `AI`/`Free`/`POS`/`Founder`/`نظم` consistent. `Preview` (recovery-match) unique and matches page terminology.
- **Fix:** orchestrator badge `"Recovery"` → `"Pilot"` (was redundant with its own label "Recovery Engine" and collided with the "Recovery Match" tool).

### 14. Accessibility
- **Proof:** audit counted 9 unlabeled icon-only buttons; 5 `aria-label`s total.
- **Fix:** added `aria-label`s to: Toast close, team member remove, team invite resend, AlertCardExpanded expand + dismiss, MobileNav More/close, Header mobile toggle, and `Input.tsx` password visibility toggle (the one real axe **critical** finding).
- **Tooling:** added `jsdom` + `axe-core` devDeps; `scripts/check_a11y.mjs` scans all 28 statically-built pages. **Result: 28/28 PASS, 0 serious violations.** Wired into CI after build.

---

## Server auth surface gap (findings, not fixed — needs decision)

`middleware.ts` `PROTECTED_SEGMENTS` does **not** include: `inventory`, `inventory/expiry`, `forecast`, `chat`, `suppliers`. These are still protected client-side via `(dashboard)/layout.tsx`, but the server renders them for unauthenticated requests (redirect happens in browser). For a `mid`-strength auth posture, add these segments to `PROTECTED_SEGMENTS`. (Filed as a recommendation — changing auth posture needs sign-off.)

## Flagged for founder sign-off
See `NAMING_DECISIONS.md` for: (a) Orchestrator/Recovery-Match naming, (b) first-run redirect to Money Audit, (c) auth-surface extension above.
