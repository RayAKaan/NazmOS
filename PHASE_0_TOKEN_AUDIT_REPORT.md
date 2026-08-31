# Phase 0 — Design Token Audit Report

**Project:** NazmOS frontend · Design System Consolidation
**Date:** 2026-08-31 · **Baseline:** `3b9bab8` (clean tree)
**Scope:** every color class / CSS var referenced in `frontend/src`
(TSX/TS only; CSS vars read from `globals.css`, definitions from `tokens.json`)
**Authoritative sources:** `frontend/design-tokens/tokens.json`,
`tailwind.config.ts` (generated), `src/app/globals.css` (generated mirror).

---

## 1. Purpose

This report is the Phase 0 checkpoint of the Consolidation mission. It
inventories every token, documents the legacy→canonical mapping that Phase 2
(`mapping.json`) will machine-read, flags conflicts the migration will
encounter, and classifies every expected visual delta. It ends with the exact
batch plan executed in Phase 3.

---

## 2. The token model

Tokens live in `frontend/design-tokens/tokens.json` and are generated into
`tailwind.config.ts` + `globals.css`. The app forces dark mode
(`layout.tsx:62`, `className="dark"`), so **canonical light/dark pairs resolve
to their dark values at render time**. All decisions below assume dark-mode
rendering.

Tailwind aliases all tokens through `oklch(var(--x) / <alpha-value>)`, so the
legacy "name" of a color (e.g. `text-navy-muted`) is only a shorthand for a
raw OKLCH literal. There are **no raw color literals** in component code
(enforced by `no-raw-color`).

---

## 3. Canonical vocabulary (the destination)

Three tiers (from README.md):

- **Tier 1 — `brand.*`** (raw primitives): **kept**.
- **Tier 2 — shadcn semantic + chart/product anchors**: the migration target.
- **Tier 3 — `intelligence.*`, `chat.*`, `whatsapp.*`**: kept.

Current canonical usage (line-matches across `src`, excl. node_modules):

| Token | Uses | | Token | Uses |
|------|-----|-|------|-----|
| `border-border` | 129 | | `text-muted-foreground` | 145 |
| `text-primary` (gold) | 125 | | `text-secondary` (teal) | 102 |
| `bg-primary` | 58 | | `text-destructive` | 49 |
| `bg-primary-foreground` | 19 | | `bg-card` | 27 |
| `bg-success` | 21 | | `bg-warning` | 19 |
| `text-warning` | 42 | | `bg-background` | 14 |
| `text-foreground` | 65 | | `bg-muted` | 14 |
| `bg-destructive` | 26 | | `bg-accent` | 10 |
| `text-accent` | 11 | | `bg-secondary` | 24 |
| `text-success` | 50 | | `border-input` | 1 |

Zero usage (safe to treat as reserved / consultative):
`bg-popover`, `text-card-foreground`, `text-popover-foreground`,
`bg-secondary-foreground`, `text-secondary-foreground`, `ring-ring`,
`bg-primary-foreground`*, `text-primary-foreground`* (*exist as tokens but
their practical uses are `text-primary` on `bg-primary` — see §9 caveats).

**Chart anchors** used via CSS vars in components (not utility classes):
`var(--chart-1..5)`, `var(--chart-grid)` in `SalesChart`,
`HealthScore`, `ReorderModal`, `KPICardAnimated`.

---

## 4. Legacy tokens bound for migration¹

### 4.1 `navy.*` — the dominant legacy family

| Token | Uses | ↘ canonical | Δ (dark) |
|------|-----|-----------|---------|
| `text-navy-muted` | 66 | `text-muted-foreground` | 63.50% → 64.0% (0.012) |
| `text-navy-text` | 58 | `text-foreground` | 95.66% → 93.0% |
| `bg-navy-panel` | 21 | `bg-card` | 22.84% → 19.2% |
| `bg-navy-panel-2` | 23 | `bg-muted` | 29.43% → 24.0% |
| `border-navy-panel-2` | 9 | `border-border` | 29.43% → 26.0% |
| `divide-navy-panel-2` | 5 | `divide-border` | → 26.0% |
| `bg-navy-panel-3` | 4 | `bg-muted` | 35.70% → 24.0% |
| `text-navy-faint` | 2 | `text-muted-foreground` | 46.03% → 64.0% |
| `bg-navy-deep` | 1 | `bg-background` | 17.43% → 15.85% |
| `bg-navy-deep-2` | 1 | `bg-popover` (floating dd) | 19.03% → 21.0% |
| `text-navy-chip` | 1 | `text-muted-foreground` | 79.04% → 64.0% |
| `text-navy-faint-2` | 1 | `text-muted-foreground` | 51.76% → 64.0% |

¹ "bound for migration" = referenced in `src` today. Zero-usage legacy token
definitions are prune-only (§7).

### 4.2 `bg.*` surface ladder

| Token | Uses | ↘ canonical | Δ (dark) |
|------|-----|-----------|---------|
| `bg-bg-primary` | 5 | `bg-background` | 14.73% → 15.85% |
| `bg-bg-secondary` | 12 | `bg-card` | 17.76% → 19.2% |
| `bg-bg-tertiary` | 16 | `bg-muted` | 20.46% → 24.0% |
| `bg-bg-tertiary/50` | 1 | `bg-muted/50` | — |
| `hover:bg-bg-hover` | 3 | `hover:bg-surface-hover` | no-op → 22.5% (F-03) |

### 4.3 `text.*` text ladder

| Token | Uses | ↘ canonical | Δ (dark) |
|------|-----|-----------|---------|
| `text-text-primary` | 53 | `text-foreground` | 94.61% → 93.0% |
| `text-text-secondary` | 83 | `text-muted-foreground` | 71.55% → 64.0% |
| `text-text-muted` | 158 | `text-muted-foreground` | 55.55% → 64.0% |

### 4.4 `status.*` → semantic

| Token | Uses | ↘ canonical | Δ (dark) |
|------|-----|-----------|---------|
| `text-status-error` | 9 | `text-destructive` | 71.06% → 63.68% |
| `bg-status-error/10` | 6 | `bg-destructive/10` | — |
| `border-status-error/30` | 5 | `border-destructive/30` | — |
| `text-status-success` | 5 | `text-success` | 80.03% → 62.12% |
| `bg-status-success/10` | 4 | `bg-success/10` | — |
| `border-status-success/30` | 3 | `border-success/30` | — |
| `text-status-info` | 4 | `text-secondary` | 71.37% → 70.38% (D-01) |
| `bg-status-info/10` | 4 | `bg-secondary/10` | — |
| `border-status-info/30` | 4 | `border-secondary/30` | — |
| `text-status-warning` | 3 | `text-warning` | 83.69% → 78.82% |
| `bg-status-warning/10` | 3 | `bg-warning/10` | — |
| `border-status-warning/30` | 3 | `border-warning/30` | — |
| `bg-status-info` (solid badge) | 1 | `bg-secondary` | — |

### 4.5 Others

| Token | Uses | ↘ canonical |
|------|-----|-----------|
| `border-border-primary` | 0 | prune definition only |
| `border-border-secondary` | 0 | prune definition only |
| `to-bg-secondary` (gradient) | 1 | `to-card` |
| `bg-text-muted/20` (chip) | 1 | `bg-muted/40` or `bg-muted/20` (D-04) |
| `text-bg-primary` | 1 | `text-primary-foreground` (ButtonWithIcon) |
| `placeholder-navy-faint` | 1 | `placeholder:text-muted-foreground` |

---

## 5. Top migration hotspots (pre-existing legacy-file distribution)

| File | legacy class hits |
|-----|------------------|
| `src/app/(dashboard)/integrations/page.tsx` | 45 |
| `src/app/(dashboard)/team/page.tsx` | 40 |
| `src/components/upload/ColumnMapper.tsx` | 37 |
| `src/components/dashboard/AlertCardExpanded.tsx` | 35 |
| `src/app/(dashboard)/chain/page.tsx` | 34 |
| `src/components/ui/Toast.tsx` | 29 |
| `src/app/(dashboard)/forecast/page.tsx` | 24 |
| `src/app/(dashboard)/upload/page.tsx` | 21 |
| `src/components/intelligence/IntelligenceChat.tsx` | 19 |
| `src/app/(auth)/onboarding/page.tsx` | 17 |
| `src/components/money-audit/TimeMachine.tsx` | 15 |
| `src/components/dashboard/KPICardAnimated.tsx` | 14 |
| `src/components/ui/CommandMenu.tsx` | 14 |
| `src/app/(dashboard)/money-audit/page.tsx` | 13 |
| `src/app/(dashboard)/feed/page.tsx` | 12 |
| `src/components/money-audit/DecisionComparison.tsx` | 12 |
| `src/app/mobile/page.tsx` | 11 |
| `src/app/(dashboard)/settings/autonomy/page.tsx` | 11 |
| `src/components/inventory/ReorderModal.tsx` | 11 |
| `src/components/money-audit/TopDecisions.tsx` | 10 |
| `src/components/pilot/RecommendationInbox.tsx` | 10 |
| `src/app/(dashboard)/inventory/expiry/page.tsx` | 10 |

**Per-prefix totals (src):**

| Prefix | count |
|--------|------|
| `text-text-*` | 294 |
| `text-navy-*` | 128 |
| `bg-navy-*` | 50 |
| `bg-bg-*` | 37 |
| `border-navy-*` | 9 |
| `divide-navy-*` | 5 |
| `border-border-primary/secondary` | 0 |
| `text-status-*` | 21 |
| `bg-status-*` | 18 |
| `border-status-*` | 15 |
| **total legacy class references** | **577** |

Plus `brand-*` 1048 (kept), `whatsapp-*` 84 (kept), `intelligence-*` 7 (kept),
`chat-*` 6 (kept), `accent-*` ⚠ 17 (kept, lint-exempt).

---

## 6. Findings — things the migration must NOT "fix" silently

**F-01 — `DecisionLogTable` already deleted.** Zero files, zero references.
Phase 6 has no work here; no action.

**F-02 — `bg-surface` is a dead class.** 62 uses site-wide, but there is no
`colors.surface` (only `surface-hover`, plus namespaced `bg.surface` /
`accent.surface` / `intelligence.surface`). `bg-surface` emits **no CSS**.
Legacy `--bg-surface` remains defined but unused by utilities. Decision:
leave classes as-is (behavior-preserving — surfaces simply render the parent
background today); do NOT mass-rewrite to `bg-bg-surface`, which would be an
unintended visual change. Logged for human review.

**F-03 — `hover:bg-bg-hover` is a dead hover.** Always resolves to nothing;
assigned in `AlertCardExpanded`. Mapping this class to `hover:bg-surface-hover`
will *activate* a previously dead hover state — an intentional interaction
repair, tracked as EXPECTED CONSOLIDATION, flagged in Phase 4.

**F-04 — `bg-bg-warm` / `bg-bg-surface` / `text-text-subtle` / `chart-literals`
/ `border-literal` have zero utility usage.** Definitions only. Migrate to
prune-only entries in `mapping.json`; remove CSS vars in Phase 6 after
verification.

**F-05 — `§` (§2/§3/§4 chef references) appears 61 times, all in comments.**
Rendering-safe; not a token issue. Left untouched.

---

## 7. Zero-usage artifacts slated for Phase 6 prune

| Artifact | Kind | Reason |
|----------|------|--------|
| `--chart-literals-*` (15 vars) | CSS var | confirmed 0 references in src |
| `--border-literal-primary/secondary` | CSS var + tw keys | 0 utility usage |
| `bg.navy`, `navy.*`, `bg.bg`, `text.text`, `status.*` blocks | tokens.json + css | after migration reaches 0 |
| `legacyLiteralColors` legacy sections | tokens.json | after B9 |
| `extraction-report.json` | stale B0 | superseded by this report |

`DecisionLogTable` (F-01) needs no prune.

---

## 8. Lint / test wiring relevant to the migration

- `no-raw-color` (cached baseline `eslint-rule-baseline.json`): allowlist
  includes everything versioned in `tokens.json`, so migrating token→token
  cannot trip it.
- `destructive-needs-action`: fires on `text-destructive|text-warning|
  text-brand-red|text-brand-amber|…` + currency content **without a sibling
  action**. Today `text-status-error/warning` are **exempt** (not in the
  regex). After migration these become `text-destructive`/`text-warning` and
  the rule **activates mid-migration** — see decision D-02.

---

## 9. Decisions & conflicts requiring sign-off

**D-01 — `status.info` has no canonical sibling.** Mission Tier-2 has
`success/warning/destructive` but no `info`. Closest canonical hue is
`secondary` (teal, 70.38%) which is already the brand accent; `chart-3`
(a 62.31% blue) is chart-only. **DECIDED (user sign-off):** `status.info →
secondary` — canonical "supporting chrome / info accent" role. Rejected:
chart-3 (chart-only), keeping the literal (violates single-layer goal).

**D-02 — status→destructive activates the *action-pair* lint rule.**
`text-status-error` today escapes `destructive-needs-action`. Migrating it to
`text-destructive` in money/badge/toast contexts newly trips the rule
(e.g. `AIReasoningPanel`, `RecommendationInbox`, `IntelligenceChat`).
**DECIDED (user sign-off):** migrate everything, keep the rule strong, and add
*justified, reason-documented* baseline entries for message-only sites whose
content is not a monetary figure. No attribute of the rule worsens; no sibling
action buttons added (would be a prohibited behavior change).

**D-03 — typography conflict (money font).** `tokens.json` `typeScale.money`
declares money figures "ALWAYS --font-sans … never serif", but the mission
spec orders a display serif for headline money/KPI figures and `MoneyKpi.tsx`
already renders `font-serif font-black text-4xl`. **DECIDED (user sign-off):
mission wins.** `typeScale.money` doc string is updated in Phase 1; Phase 4
caption expects the serif delta on headline money/KPI figures only.

**D-04 — `bg-text-muted/20` cross-namespace chip.** Legacy `colors.text.muted`
(55.55%) used at 20% alpha as a chip tint in `TopProducts`. Canonical
`muted` is 24.0%; 20% is nearly invisible on dark. **Proposed:** `bg-muted/40`
(8-9% L-ink pass on dark) — nearest visible equivalent. Flagged as EXPECTED
CONSOLIDATION.

**D-05 — `text.text.bg` cross-namespace in `ButtonWithIcon` (1 use).**
`text-bg-primary` (14.73% ink) on `bg-accent-primary` (gold) → canonical
`text-primary-foreground` (15.85% ink on gold). Zero-delta-ish; EXPECTED.

**F-02 — `bg-surface` (62 uses) dead class — DECIDED (user sign-off): leave
dead.** It emits no CSS today and renders the parent background; rewriting it
would be an unintended visual change. Logged, not "fixed".

**F-03 — `hover:bg-bg-hover` dead hover — DECIDED (user sign-off): map to
`hover:bg-surface-hover`.** Activates a previously-dead hover state; tracked as
EXPECTED CONSOLIDATION (interaction repair).

---

## 10. Phase-4 classification policy

Each before/after pair on the reference device:
- `EXPECTED CONSOLIDATION` — hue-similar canonical swap, dead-hover activation,
  info→secondary, status→success dimming, muted ladders collapsing.
- `UNINTENDED REGRESSION` — anything else. Blocks the batch.

---

## 11. Phase 3 batch plan (payloads, per mission order)

| # | Batch | Entry files (hotspots ensure coverage) |
|---|-------|---------------------------------------|
| 1 | **chain** | `(dashboard)/chain/page.tsx`, `integrations`, `team`, `settings/autonomy` |
| 2 | **dashboard** | `dashboard/page.tsx`, `ActionCenter`, `AlertCard{Expanded}`, `KPICard{T}` (+Animated), `QuickActions`, `TopProducts`, `HealthScore`, `DeadStock`, `MobileActionCenter`, `Toast`, `Badge`, `Card`, `Input`, `SeamBorder`, `CommandMenu` |
| 3 | **pages** | `forecast`, `upload`, `feed`, `inventory{/expiry, /ReorderModal, InventoryTable, InventoryFilters}`, `suppliers`, `ops`, `orchestrator`, `mobile`, `partners`, `(auth)/onboarding` |
| 4 | **money-audit** | `money-audit/page.tsx`, `TimeMachine`, `TopDecisions`, `DecisionComparison`, `MoneyRecoveryMap`, `AIReasoningPanel` |
| 5 | **landing** | `app/page.tsx`, `product-demo`, `components/landing/**`, `not-found` |
| 6 | **everything remaining** | any file still containing legacy classes; then prune vars (§7) |

Each batch: standalone commit + `tsc` + eslint + jest + build + Playwright
baseline verdict.

---

## 12. Done in this phase

- [x] Full token inventory (canonical + legacy + zero-usage) with counts.
- [x] Mapping table for `navy.*`, `bg.*`, `text.*`, `status.*`, borders,
      gradients, cross-namespace quirks.
- [x] Hotspots ranked; batch payloads derived from real file distribution.
- [x] Conflict findings F-01..F-05 and sign-off decisions D-01..D-05.
- [x] `frontend/design-tokens/README.md` written (contract).
- Status: **AUDIT COMPLETE — mapping is deterministic; two sign-offs (D-01,
  D-02) outstanding and two verdict-sensitivities (F-02, F-03) logged.**

Next: Phase 2 — emit `frontend/scripts/token-migration/mapping.json`.