# Redesign Implementation Status (v2 brief + v3 visual-polish addendum)

Date: 2026-08-19 · **ALL stages complete** — v2 stages 1–7 + v3 addendum.

---

## v3 addendum — shipped (verified)

### §A Elevation system
- `tokens.json` → 3 shadow levels: `elevation-1/2/3` (generate `shadow-elevation-*`).
- `Card`: level-1 default; `trim="weave"` → level-2 + `-translate-y-0.5` (2px, 150ms)
  + `hover:border-primary/30` (brand-gold @ 30%, matching §A's `oklch(75.41% 0.085 67.1)`).
- level-3 reserved for modal/popover (token ready; not yet applied — no modal in scope yet).

### §B Motion (framer-motion only — no new animation lib)
- `FigureHeadline`: counts up on mount/change via `@number-flow/react` (already installed,
  previously unused — now used). No second animation library.
- `ShineBorder`: gold beam traveling the border (BorderBeam technique, framer-motion),
  ~6s idle cycle — primary CTA only.
- `SplitText`: one-time word reveal (hero headline).
- `Marquee`: seamless continuous scroll (merchant logo strip).
- No ambient looping noise on product screens — only brand-forward (see §C).

### §C Ambient background (Login + Landing hero only)
- `AmbientBackground`: two slow blurred blobs, `--brand-gold` / `--brand-teal` @ 7–8% opacity.
- Applied to landing hero + `/login`. Grain (`.grain`) added to login dark surface.

### §D Landing
- Hero headline → `SplitText` one-time reveal.
- Merchant strip → `Marquee` ("Recovery systems at work across the Kingdom").
- Primary CTA → `ShineBorder` gold beam.
- (FeaturesBento hover-lift: n/a — see finding below.)

### §Typography
- `FigureHeadline` primary 800 (`font-extrabold`), secondary 700 (`font-bold`).
- Large figures `tracking-[-0.03em]`.

## Finding — `components/landing/*` is dead code
`Hero`, `FeaturesBento`, `FeatureSection`, `StorySection`, `CTASection`, `Footer`,
`Navbar`, `GradientText`, `ShimmerButton`, `MagneticButton`, `ScrollIndicator`,
`RevealOnScroll` are all **defined but never imported** — the real landing page is
self-contained in `app/page.tsx` (which uses `brand-*` tokens). Only `GuestAuditUploader`
is used. v2 §5's references to `Hero.tsx`/`FeaturesBento.tsx` are stale.
→ v3 polish was applied to `app/page.tsx` directly; the dead files remain candidates for
the final removal pass (v2 §9 "retire ShimmerButton" is already satisfied — it's unused).

## Verification (all green)
| Gate | Result |
|---|---|
| `npm run build` | ✅ 37 routes, 0 errors |
| `npm run lint` | ✅ 0 errors (no new raw-color / destructive-without-action) |
| `npm test` | ✅ 9 passed / 2 suites |
| Brand-forward pages | ✅ `/`, `/login`, `/register`, `/onboarding`, `/ui-kit` → 200 |
| Auth guard | ✅ `/dashboard`, `/money-audit`, `/recovery-match` → 307 → /login (intended) |
| WCAG contrast | ✅ gold/night 8.73, gold/light 5.00 (unchanged) |

## Core-product pass (v2 §5, this turn)
- **Brand-forward screens:** `/register` + `/onboarding` now carry the same §C ambient
  aurora + grain as `/login` (onboarding card also moved to `rounded-lg shadow-elevation-3`).
- **Dashboard:** `KPIGrid` → shared `BentoGrid` + `Card trim="weave"` (level-2) +
  `FigureHeadline` count-up; inline `p-5 rounded-xl bg-surface` wrappers → `Card density="data"`.
- **Money Audit:** 3 headline KPIs → `FigureHeadline` (semantic `tone`); `ActionCard` →
  `SeamBorder` (suggested=idle, approved=resolving, completed=recovered gold seam).
- **Recovery Match:** `MatchCard` → `SeamBorder` (completed=recovered, rejected=idle, else
  resolving); completed tab gets a `FigureHeadline` "Total recovered value" (success tone).
- **`FigureHeadline`** gained an optional `tone` prop (default/gold/success/destructive/
  warning) — the one deliberate API extension beyond the v2 §4 contract, flagged here per §10.


## Done

### Stage 1 — Step-zero audit  → `design-tokens/STEP_ZERO_AUDIT.md`
Full inventory: live raw-color sources, 71 ad-hoc `grid-cols-*` sites, 112 `p-6` sites,
334 `rounded-xl/2xl/3xl` sites, 17 `toLocaleString` (vs 3 `Intl.NumberFormat`) files,
icon `strokeWidth` drift, and dead code (`ShimmerButton`, `GradientText`, `MagneticButton`,
`ScrollIndicator` — all defined but never imported).

### Stage 2 — Token diff  → `design-tokens/tokens.json` + `scripts/build_design_tokens.ts`
- **Radius (§2.3):** 3-tier + cap — `sm 4px / md 6px / lg 8px`, `xl/2xl/3xl` capped at 8px.
- **Motion (§2.4):** `--ease-standard`, `--duration-fast/base/seam/weave` (+ `seam-reveal`,
  `weave-in` keyframes, CSS-driven per §6).
- **Typography (§2.2):** modular 1.25 scale xs→9xl; drives Tailwind `fontSize` + `--text-*`
  vars. Money figure now `font-sans tabular-nums`, never serif.
- **Weave (§3):** `--weave-accent`, `--weave-accent-teal`, `--weave-opacity-bg` (dark 0.04 /
  light 0.016).
- **Light/dark reconciliation (§2.5):** dark is primary; light weave = 40% intensity. Stated
  as a code comment in `globals.css` so it isn't "fixed" back to parity.
- Tokenized the generator's static-CSS raw colors (`.shadow-glow*` → `oklch(var(--primary))`).
- **Fixed `npm run build:tokens`** — was `node scripts/build_design_tokens.ts`, which Node 20
  cannot execute (`.ts` extension). Now `tsx scripts/build_design_tokens.ts` (+`tsx` dev dep).

### Stage 3 — Primitives (new `src/components/ui/`)
`WeaveTile` (field + chevron, mask-data-URI background — no per-instance SVG bloat),
`WeaveSprite` (single `<symbol>` sprite, mounted once in `layout.tsx`), `ChevronDivider`,
`SeamBorder` (kintsugi state machine), `BentoGrid`, `FigureHeadline`, reworked `Card`
(density/trim/variant/hoverable). Reference route: **`/ui-kit`**.

## Verification (all green)

| Gate | Result |
|---|---|
| `npm run build` | ✅ 37 routes, 0 errors |
| `npm run lint` | ✅ 0 errors (no new `no-raw-color` / `destructive-needs-action`) |
| `npm test` | ✅ 9 passed / 2 suites |
| Backend `pytest` | ✅ 374 passed, 90 skipped, 2 errors (Postgres-only RLS tests — no PG in sandbox) |
| Backend boot | ✅ uvicorn + SQLite, `/health` → healthy, 174 API paths |
| WCAG contrast (§8) | ✅ gold/bg 8.73, gold/card 8.25, gold/light-bg 5.00, red/card 4.88 … all ≥4.5 |
| RTL | ✅ new geometry is symmetric/direction-agnostic (verified by construction) |

## Flagged conflicts (§10 "do not silently work around")

1. **`destructive-needs-action` vs FigureHeadline trend** — the rule fires only on literal
   digits in a literal `text-destructive` element; FigureHeadline's trend is prop-driven,
   so no violation today. But a future page hard-coding a negative figure *inside* a
   `text-destructive` element without an action will trip it (by design). Note for stage 5.
2. **`manifest.json` / `viewport.themeColor`** — JSON/meta color values cannot reference CSS
   vars; kept as literal hex, synced to `--brand-night` / teal by hand (see audit §1).

## Stage 6 — shared-component + icon sweep (done)
- **Icon standardization (§5):** uniform at the default 2; standardized to **1.75 globally**
  via `.lucide { stroke-width: 1.75 }`. **Gotcha:** it must live OUTSIDE `@layer` — Tailwind
  purges custom `@layer` class rules whose selector never appears in scanned source (lucide's
  class is only added at runtime). Verified in built CSS: `.lucide{stroke-width:1.75px}`.
- **SalesChart:** tooltip → `Card density="data"` + `shadow-elevation-2`; gridlines/accents
  already on `--chart-grid` / `--chart-1/3`.
- **Elevation:** `HealthScore` + `AlertCard` → `shadow-elevation-1`.
- **Metadata images (§5):** `icon/opengraph/twitter-image.tsx` were off-palette; recolored to
  `--brand-*` seeds. **Flag:** Satori has no CSS-var access → literal hex (module-level consts,
  which `no-raw-color` exempts, matching the original pattern).
- **Favicon fix (pre-existing):** metadata + manifest pointed at `/icon.png` (404) → repointed
  to the real `/icon` route.

## Stage 7 — final QA + dead-code removal (done)
- **Removed dead landing code:** `Hero`, `FeaturesBento`, `FeatureSection`, `StorySection`,
  `CTASection`, `Footer`, `Navbar`, `GradientText`, `ShimmerButton`, `MagneticButton`,
  `ScrollIndicator`, `RevealOnScroll` (all 0-reference; only `GuestAuditUploader` remains).
- **`glow-gold`** (retired ShimmerButton pattern) confirmed unused in live code — §9 satisfied.
- **Left in place (flagging):** `AlertCardExpanded`, `KPICardAnimated`, `WhatsAppAlertButton`,
  `CommandMenu` are 0-reference dead, but v2 §5 lists them as "touch once" — not removed.
- **Radius (§2.3):** enforced globally — `rounded-xl/2xl/3xl` map to 8px in the token scale.
- Final smoke: all public routes 200; auth-guarded routes 307→/login; `/demo` 308→/product-demo;
  **zero 500s**.
