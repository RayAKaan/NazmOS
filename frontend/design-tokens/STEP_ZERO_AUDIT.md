# Step-Zero Audit — NazmOS Frontend Redesign (v2)

Date: 2026-08-19 · Branch baseline: `main` (= merged `feat/design-system-tokens`, B1–B7)
Verified fresh against the working tree, not the (stale) B0 scan artifacts.

Baseline health before any changes:
- `npm run build` → ✅ 36 routes, 0 errors
- `npm run lint` → ✅ 0 errors, 6 warnings (all pre-existing `window.location.href` + 1 anon-export)
- `npm test` → ✅ 9 passed / 2 suites
- ESLint baselines are **empty** (`no-raw-color: []`, `destructive-needs-action: []`) → the
  codebase is currently at **zero** raw-color / destructive-without-action violations.

---

## 1. Raw color inventory (the real one)

`design-tokens/extraction-report.json` is a **stale B0 snapshot** — it lists hundreds of hex
literals in `tailwind.config.ts`, but that file is now generated and contains only
`oklch(var(--…))` references. The `#hex` entries in the report are historical, not live.

**Live raw hex/rgb remaining (outside the sanctioned `tokens.json` source of truth):**

| Location | Value | Note |
|---|---|---|
| `public/manifest.json` | `background_color: "#0A0E0C"`, `theme_color: "#0A0E0C"` | JSON manifest — cannot reference CSS vars; must stay literal hex but should be kept in sync with `--brand-night`. **Flag for §5.** |
| `scripts/build_design_tokens.ts` static utilities | `rgba(203,179,138,…)`, `rgba(19,160,90,…)`, `rgba(255,255,255,0.02)`, `rgba(0,0,0,…)`, `rgba(212,165,116,…)`, `rgba(20,184,166,…)` in `.grain` / `.shadow-glow*` / `.shadow-subtle` | These are **hand-written in the generated CSS block**, not token-derived. They bypass the token system. **Flag: this is the one place raw color still actually lives.** |
| `src/app/icon.tsx`, `opengraph-image.tsx`, `twitter-image.tsx` | (to verify) | Image generators — likely hardcoded colors; must use tokens or documented literal constants. |
| `design-tokens/tokens.json` → `legacyLiteralColors` | all legacy hex | **Sanctioned** (this *is* the source of truth). Not a violation. |

The `#f2cf69` / `#d4a574` / `#ef4444` etc. that the brief flags are **legacy aliases inside
tokens.json**, already tokenized. No action needed beyond the manifest + static-CSS + image files.

## 2. Ad-hoc `grid-cols-*` usage (71 occurrences, ~30 files)

Notable clusters (candidates for the shared `BentoGrid` primitive in §4):

- `components/dashboard/KPIGrid.tsx` — `grid-cols-4`/`grid-cols-2` (two places)
- `components/dashboard/AlertSection.tsx` — `grid-cols-3`/`2`
- `components/dashboard/QuickActions.tsx` — `grid-cols-3`
- `components/landing/FeaturesBento.tsx` — `grid-cols-2` (named "bento" but hand-rolled)
- `components/landing/FeatureSection.tsx` — `grid-cols-3`/`2`
- `app/product-demo/page.tsx` — **13 distinct `grid-cols-*`** (worst offender)
- `app/page.tsx` (landing) — 4
- `app/partners/page.tsx`, `components/upload/ColumnMapper.tsx`, `ReorderModal.tsx`,
  `FreeAuditChecklist.tsx`, `GuestAuditUploader.tsx`, `Footer.tsx`, `StorySection.tsx`, etc.

The 24×24 gap/rhythm is inconsistent (arbitrary `gap-4/6/8` mixed with `grid-cols-*`).

## 3. Spacing / radius drift

- **Radius** (the §2.3 reduction target): `rounded-xl` **157**, `rounded-2xl` **131**,
  `rounded-3xl` **46**, `rounded-full` **55** (mostly chips/badges, acceptable as `rounded-sm`
  replacement per §2.3 — badges are `sm=4px` not `full`), `rounded-lg` **46**, `rounded-md` **2**.
  Current token scale: `sm .375 / md .625 / lg .875 / xl 1.25 / 2xl 1.75 / 3xl 2rem`.
  → All `rounded-xl/2xl/3xl` must come down to ≤ `--radius-lg` (8px).
- **Padding**: `p-6/px-6/py-6` **112** occurrences = the "flat p-6 everywhere" the brief
  replaces with `p-8` (editorial) / `p-4` (data).
- `Card.tsx` hard-codes `p-6` in `CardHeader`/`CardContent`/`CardFooter`.

## 4. Money-figure / typography drift

- `MoneyKpi` (the existing money primitive) renders `font-serif font-black text-4xl md:text-5xl`
  — §2.2 requires **`font-sans` (Inter), tabular-nums, `4xl`/`3xl`**, never serif/mono.
- `Typography.tsx` `Heading`/`Display` use `font-serif` + legacy `text-text-primary` tokens
  and `text-5xl/6xl/7xl` — outside the §2.2 modular scale.
- `tokens.json` `typography.typeScale.money` still carries the serif classes.
- **Number formatting**: `toLocaleString` in **17 files**, `Intl.NumberFormat` in **only 3**
  (`chain`, `product-demo`, `lib/utils.ts`). §2.6 requires `Intl.NumberFormat` as the single path
  (a `formatCurrency` helper already exists in `lib/utils.ts` and is the consolidation point).

## 5. Icons

- Lucide icons default to `strokeWidth=2`; only 3 components set `strokeWidth={2}` explicitly.
  §5 requires a consistent `1.75`. No global wrapper exists — needs a `lucide` default via a
  shared `Icon` wrapper or a per-component sweep.

## 6. Dead / to-retire code (final-pass target, §9)

- `ShimmerButton.tsx` — defined, **never imported** (its `hover:shadow-glow-gold hover:scale-105`
  is the retired gradient/glow pattern).
- `GradientText.tsx`, `MagneticButton.tsx`, `ScrollIndicator.tsx` — defined, **never imported**.
- `glow-gold` / `glow-teal` box-shadows exist in `tokens.json` + generated config (used by ShimmerButton + others).

## 7. Missing tokens (targets for §2 / §3)

- `motion` section in `tokens.json` is **empty `{}`** — §2.4 (ease/duration/weave/seam) not yet tokenized.
- No `--space-*`-explicit 8px scale (relies on default Tailwind spacing — the *values* §2.1 wants
  (`space-4/8/12/16/24`) already exist; what's missing is the *discipline*, not the utilities).
- No `--weave-*` tokens (`--weave-accent`, `--weave-opacity-bg`) — §3 needs them.
- No `--radius-*` three-tier scale (`sm/md/lg` = 4/6/8px) — current tokens are 6-tier + `full`.
- No `--text-*` type tokens (xs…4xl) — §2.2 modular scale not present.
- Light/dark reconciliation (§2.5) has no code-level statement; light mode currently carries
  the full legacy intensity.

## 8. Kintsugi / Seam (new)

- No existing `SeamBorder` / `SeamDivider` / `seam` / kintsugi code anywhere.
- `money-audit` and `recovery-match` pages manage `resolving → recovered` state locally
  (`money_recovered_sar`, `recoveredValues`) — the hook points for `SeamState`.

## Diff-target summary (for §10 stage 3)

1. Tokenize the static-CSS raw colors in `build_design_tokens.ts` (§1).
2. Add §2.2 type scale + §2.3 radius scale + §2.4 motion + §3 weave tokens to `tokens.json`.
3. Ship `WeaveTile`/`ChevronDivider`/`SeamBorder`/`BentoGrid`/`FigureHeadline` + reworked `Card`.
4. Replace 71 ad-hoc grids with `BentoGrid`; 157+131+46 radius sites with the 3-tier scale;
   112 `p-6` sites with density-aware `p-8`/`p-4`; 17 `toLocaleString` sites with `formatCurrency`.
5. Icon `strokeWidth` 1.75 sweep; remove dead `ShimmerButton`/`GradientText`/`MagneticButton`/`ScrollIndicator`.
