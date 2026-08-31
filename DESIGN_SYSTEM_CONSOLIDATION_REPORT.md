# Design System Consolidation — FINAL REPORT

> **Scope:** frontend-only. No backend code was modified, no Tailwind upgrade,
> no runtime dependencies added, no paid/external visual-regression service.
> Each phase was implemented and committed independently.
>
> **Verification labels used:** **VERIFIED** = demonstrated locally + CI checks pass;
> **PARTIAL** = tooling works but full run blocked by an out-of-scope prerequisite;
> **NOT VERIFIED** = cannot be demonstrated in this environment.

---

## 1. Objective

Consolidate every legacy color namespace into a **single semantic token layer**,
so one design decision updates the whole product without restyling drift:

| Tier | Namespace | Role |
|---|---|---|
| Tier 1 | `brand.*` | Brand palette primitives |
| Tier 2 | semantic vocab (`background`, `foreground`, `card`, `muted`, `border`, `primary`, `success`, `warning`, `info`, `destructive`, …) | Canonical semantic tokens |
| Tier 3 | `intelligence.*` / `chat.*` / `whatsapp.*` | Feature-specific semantic aliases |

Source of truth: `frontend/design-tokens/tokens.json` → auto-generates
`tailwind.config.ts` + `globals.css` via `npm run build:tokens`.

---

## 2. Phase Status

| Phase | Deliverable | Status | Evidence |
|---|---|---|---|
| 0 | Token audit + source-of-truth | **VERIFIED** | `PHASE_0_TOKEN_AUDIT_REPORT.md`; `design-tokens/tokens.json` |
| 1 | Migration mapping | **VERIFIED** | `scripts/token-migration/mapping.json` |
| 2 | Codemod (`migrate.ts`) | **VERIFIED** | `scripts/token-migration/migrate.ts` (exact-literal, dry-run) |
| 3 | Migration batches 1–6 committed | **VERIFIED** | 6 batch commits; `npm run lint` & `build` pass |
| 3b | Source Serif 4 serif for headline money/KPI figures | **VERIFIED** | `src/app/layout.tsx` `--font-serif` via `next/font/local` |
| 4 | Visual regression | **PARTIAL** | spec + tools done; **public** verified; **authed dashboards NOT VERIFIED** (backend blocked) |
| 5 | CI token guard | **VERIFIED** | `.github/workflows/ci.yml` job + local `check_legacy_tokens.mjs` (PASS, 167 files) |
| 6 | Token pruning (Phase 6 cleanup) | **VERIFIED** | pruned `status`, `navy`, `bg`, `text`, `chartLiterals` |

Overall regression gate: **`npm run lint` (0 errors), `npm run build` (ok), `npx tsc --noEmit` (ok), `npx jest --ci --runInBand` (9/9 pass)** all green after pruning.

---

## 3. Phase 4 — Visual Regression (`PARTIAL`)

### Tooling (completed, VERIFIED)
- `frontend/e2e/visual-baseline.spec.ts` — captures every route from
  `docs/FRONTEND_PAGE_MAP.md` (public + authed) and asserts `toHaveScreenshot`
  against the stored baseline, `maxDiffPixelRatio: 0.02`, 1440×900.
- Snapshot location moved to `e2e/__screenshots__/baseline/` via
  `snapshotPathTemplate` in `playwright.config.ts`.
- `frontend/scripts/capture_public_baseline.mjs` — Playwright-browser capture for
  public routes **without** requiring a backend/auth-setup.
- `frontend/scripts/visual_delta_report.mjs` — aggregates Playwright diff artifacts
  + JSON report into `frontend/_report/DESIGN_SYSTEM_VISUAL_REPORT.md` with the
  required `EXPECTED CONSOLIDATION` vs `UNINTENDED REGRESSION` classification guide.

### Baseline captured (VERIFIED — 6 public routes)
| Route | Screenshot | Result |
|---|---|---|
| `/` (landing hero) | `__screenshots__/baseline/index.png` | ✅ pass |
| `/product-demo` | `__screenshots__/baseline/product-demo.png` | ✅ pass |
| `/login` | `__screenshots__/baseline/login.png` | ✅ pass |
| `/register` | `__screenshots__/baseline/register.png` | ✅ pass |
| `/terms` | `__screenshots__/baseline/terms.png` | ✅ pass |
| `/privacy` | `__screenshots__/baseline/privacy.png` | ✅ pass |

The 6 public routes re-verified clean through the real Playwright runner
(`6 passed`). Source Serif 4 is visible on the landing hero money/KPI figures.

### Authed dashboard routes — **NOT VERIFIED**
`/dashboard`, `/money-audit`, `/chain`, `/inventory`, `/feed`, `/chat`,
`/orchestrator`, `/recovery-match`, `/upload`, `/inventory/expiry`,
`/forecast`, `/integrations`, `/ops`, `/team`, `/suppliers`,
`/settings/autonomy` require a fully working backend + seeded demo data
(authentication via `e2e/.auth/owner.json` from the `setup` project).

**Blocker (pre-existing, out of scope):** the README/docker SQLite dev stack cannot
start — `sqlalchemy[asyncio]==2.0.25` (Python <3.13) is incompatible with the
resolved newer `aiosqlite` (`>=0.19` satisfied by 0.21+):
`TypeError: 'server_settings' is an invalid keyword argument for Connection()`.
Fixing this would require editing `backend/requirements.txt` or the backend Docker
image, which **the mission forbids** (frontend-only). Per the mission rule, this is
marked **NOT VERIFIED** rather than faked.

The `visual-baseline.spec.ts` AUTHED block is in place and will pass once a
working backend is available (CI with a Postgres service would provide one).

---

## 4. Phase 5 — CI Token Guard (`VERIFIED`)

- `.github/workflows/ci.yml` gains a `token-guard` job (on PRs) that scans the
  diff for banned legacy classes and fails with a pointer to the README.
- Local mirror: `frontend/scripts/check_legacy_tokens.mjs` — **PASS: 167 files
  scanned, no banned legacy design tokens.**
- Banned set matches `design-tokens/README.md`:
  `bg-navy-`, `text-navy-`, `border-navy-`, `bg-bg-`, `text-text-`,
  `bg-status-`, `text-status-`, `border-status-`, `bg-chart-literals-`,
  `text-chart-literals-`, `border-border-primary`, `border-border-secondary`.

---

## 5. Phase 6 — Token Pruning/Exception (`VERIFIED`)

### Pruned from `legacyLiteralColors` in `tokens.json`
`status`, `navy`, `bg`, `text`, `chartLiterals`.

### Recorded exceptions
- **`borderLiteral` kept** — still in active use as `border-primary` /
  `border-secondary` (18× class usages). This is a deliberate exception even
  though `mapping.json` `pruneNamespaces` lists `borderLiteral`/`chartLiterals`;
  `chartLiterals` was pruned, `borderLiteral` was not (proof of active usage).
- Canonical Tier-2 + `brand` + Tier-3 (`intelligence`, `chat`, `whatsapp`) remain.

### Regeneration verified
`npm run build:tokens` regenerated `tailwind.config.ts` + `globals.css`.
Legacy var defs (`--status-*`, `--navy-*`, `--bg-*`, `--text-*`,
`--chart-literals-*`) are gone; canonical + brand + Tier-3 + `--border-literal-*`
remain.

---

## 6. Out of Scope / Known Gaps (not addressed — frontend-only mission)

- **Backend SQLite dev/runtime bug** (`server_settings` aiosqlite incompatibility)
  — pre-existing, backend, out of scope; blocks authed dashboard screenshots.
- **Onboarding "fake insight"** — pre-existing placeholder content, untouched.
- **Suppliers / Expiry hardcoded data** — pre-existing, untouched.
- **Missing badges** in some routes — pre-existing, untouched.
- No Tailwind upgrade, no new runtime deps, no external visual-regression service.

---

## 7. How to re-run

```bash
# tokens -> tailwind + globals
npm run build:tokens

# local banned-token gate
node scripts/check_legacy_tokens.mjs

# public baselines (no backend needed), app served at :3000
node scripts/capture_public_baseline.mjs

# visual comparison + delta report
npx playwright test visual-baseline --project=chromium   # needs backend for authed routes
node scripts/visual_delta_report.mjs                     # -> frontend/_report/DESIGN_SYSTEM_VISUAL_REPORT.md
```
