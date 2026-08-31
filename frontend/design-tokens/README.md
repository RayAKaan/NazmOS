# NazmOS Design Tokens — Single Semantic Token Layer

This document is the **operating contract** for the Design System Consolidation.
It defines the canonical token tiers, the exact set of legacy tokens that are
being migrated (per-prefix), the migration rules, and the CI enforcement that
ships in Phase 5. `tokens.json` (in this directory) remains the single source
of truth for every value; `tailwind.config.ts` and `globals.css` are generated
from it via `npm run build:tokens` (`scripts/build_design_tokens.ts`).

## Tiers

| Tier | Members | Status |
|------|---------|--------|
| Tier 1 — brand primitives | `brand.*` (value 1048 usages) | **Keep.** Named product palette (gold, teal, navy, cream, etc.). |
| Tier 2 — canonical semantic | shadcn set: `background, foreground, card, card-foreground, popover, popover-foreground, primary, primary-foreground, secondary, secondary-foreground, muted, muted-foreground, accent, accent-foreground, destructive, destructive-foreground, warning, warning-foreground, success, success-foreground, success-bright, border, input, ring` + `chart-1..5, chart-grid, surface-hover, overlay, glass, glass-border` | **Destination of all migrations.** |
| Tier 3 — product namespaces | `intelligence.*`, `chat.*`, `whatsapp.*` | **Keep.** Channel / domain-specific, single-value anchors already served by canonical tokens. |
| Legacy literals (to migrate) | `bg-navy-*`, `text-navy-*`, `border-navy-*`, `divide-navy-*`, `bg-bg-*`, `text-text-*`, `border-border-primary`, `border-border-secondary`, `text-status-*`, `bg-status-*`, `border-status-*`, `to/from/via-bg-*`, `placeholder-navy-*` | **Migrate to Tier 2, then prune.** |
| Definition-only (to prune only) | `--chart-literals-*` (15 vars), `--border-literal-primary/secondary`, `--status-*`, `--bg-surface`, `--bg-warm`, `--text-subtle` (when usage reaches zero) | **Prune definitions; zero src usage.** |

The retained legacy accents (`accent-*`, lint-exempt via `TOKEN_ACCENT`) and
the whole `brand.*` family are NOT migration targets. `bg-surface` (top-level,
64 uses) currently resolves to *nothing* (no `colors.surface` key) and is left
untouched — see the Phase 0 audit report, finding F-02.

## Banned prefixes (CI guard, Phase 5)

Any new occurrence of these class prefixes fails CI, with a message pointing at
this file:

```
bg-navy-  text-navy-  border-navy-
bg-bg-    text-text-
border-border-primary  border-border-secondary
text-status-  bg-status-
```

## Migration mapping (legacy → canonical)

The authoritative machine-readable mapping lives in
`frontend/scripts/token-migration/mapping.json` (one entry per token, incl.
`null` destinations for prune-only tokens). Convictions:

- Backgrounds: `bg-navy-deep`/`bg-bg-primary` → `bg-background`;
  `bg-navy-panel`/`bg-bg-secondary` → `bg-card`;
  `bg-navy-panel-2`/`bg-navy-panel-3`/`bg-bg-tertiary` → `bg-muted`;
  `bg-navy-deep-2` (floating dropdown) → `bg-popover`.
- Text: `text-navy-text`/`text-text-primary` → `text-foreground`;
  `text-navy-muted` → `text-muted-foreground`;
  `text-navy-faint`/`text-navy-faint-2`/`text-navy-chip`/`text-text-secondary`/
  `text-text-muted` → `text-muted-foreground` (single muted tier).
- Borders / dividers: `border-navy-panel-2` → `border-border`;
  `divide-navy-panel-2` → `divide-border`;
  `border-border-primary`/`border-border-secondary` → prune (zero usage).
- Focus ring offset (`.focus-ring` utility in `build_design_tokens.ts`, emitted into
  `globals.css`): `focus-visible:ring-offset-bg-primary` → `ring-offset-background`.
- Status: `text/bg/border status-*` → canonical:
  `success → success`, `warning → warning`, `error → destructive`,
  `info → secondary`. See decision D-01 in the audit report.
- Dead classes resolved by migration: `hover:bg-bg-hover` →
  `hover:bg-surface-hover` (previously a silent no-op).

Every mapping is an **exact literal replacement** (same shorthand family, same
utility prefix, opacity modifiers preserved verbatim).

## Governance rules

1. No new raw color literals in source (enforced by `no-raw-color` ESLint rule,
   values only in `tokens.json`).
2. No arbitrary-value color classes in source.
3. Any value rendered in `destructive`/`warning` MUST have a sibling action
   control in the same visual unit (`destructive-needs-action` rule; also runs
   against `brand-red`/`brand-amber` text). Migrating `status-error` →
   `destructive` **activates** this rule on previously-exempt sites — verified
   per batch (see audit report, D-02).
4. Typography: headline money/KPI figures use the display serif
   (`--font-serif`, Phase 1). NOTE: `tokens.json` `typeScale.money` currently
   says "ALWAYS --font-sans, never serif" — **superseded** by this mission.
   `MoneyKpi.tsx` already uses `font-serif`; the old document conflicts with
   current product usage (see audit report, D-03).
5. `gold`/`primary` is reserved (5-10% screen coverage) and `secondary` (teal)
   must never render the primary financial number.
6. After each batch: `tsc`, eslint, jest, build, Playwright baseline. Every
   side-by-side component states it must be pixel-identical; any delta classed
   either `EXPECTED CONSOLIDATION` or `UNINTENDED REGRESSION`.

## Files

- `tokens.json` / `tokens.schema.json` — single source of truth.
- `scripts/build_design_tokens.ts` — generator `npm run build:tokens`.
- `scripts/token-migration/mapping.json` (Phase 2) — migration lookup.
- `scripts/token-migration/migrate.ts` (Phase 3) — exact-literal renamer,
  `--dry-run` + per-batch modes.
- `PHASE_0_TOKEN_AUDIT_REPORT.md` (repo root) — inventory, counts, decisions.