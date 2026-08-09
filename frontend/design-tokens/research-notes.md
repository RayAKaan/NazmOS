# Design System Research Grounding (B0)

Captured before authoring tokens. Sources consulted and how they shape the token set.

## 1. shadcn-fintech (nearest-category reference)
- URL: https://github.com/abderrahimghazali/shadcn-fintech
- Pattern confirmed: **dark-dominant surface, color reserved for meaning**.
  - Full dark/light mode via CSS variables (single globals.css, `.dark` block).
  - Recharts for charts, dark surfaces with muted chrome (grid/axis), accent used sparingly
    for money movement / positive/negative deltas.
  - Coverage lesson for NazmOS: the money figure is the highest-contrast element on a
    near-neutral dark surface; chroma is reserved for signal, not decoration.
- Applies to: `--background` dominance rule, `--primary` gold scarcity rule,
  chart palette guidance (muted grid, accent lines).

## 2. Style Dictionary (amzn / style-dictionary)
- Pattern: **tokens defined once (JSON/DTCG), platform outputs generated** — never hand-written CSS.
- DTCG (Design Tokens Community Group) format is the forward-compatible spec; we align loosely:
  `$schema`, `$value`, `$type` concepts. We use a pragmatic `{ light, dark }` pair per color
  plus a `usage`/`coverage` intent field, and generate `globals.css` + `tailwind.config.ts` from it.
- Applies to: `design-tokens/tokens.json` is the single source of truth; everything else is generated.

## 3. tweakcn.com (theme preview/editor)
- Reference for OKLCH-based Tailwind theme generation and previewing light/dark pairs.
- Notes: keep light and dark pairs same-hue-family with lightness inverted; use low chroma
  for surfaces, high chroma only for the semantic accents (gold/teal/green/red/amber).
- (Interactive site; used as a mental model, not scraped.)

## 4. tailwind-design-system skill (wshobson/agents)
- Applied: its **OKLCH token principles and color-system hierarchy** (Brand → Semantic → Component).
- Explicitly NOT applied: Tailwind v4 `@theme` CSS-first config. This codebase stays on
  Tailwind v3.4; generation targets `tailwind.config.ts` (v3 format) + CSS custom properties.
  A v4 upgrade is a separate, higher-risk change and is out of scope (user decision, B0).

## 5. billingsdk.com / billui
- Deferred to B8 (System Behavior settings page: plan & billing section).
- Will use shadcn component patterns + billingsdk-style plan/settings layout when building the page.

## 6. Money-psychology constraints (from task, enforced in tokens.json + lint)
- `--background`: near-black `#0A0E0C` dominant surface (large majority of screen area).
- `--primary` (gold `#d4a574`): reserved — CTAs, active nav, logo, EARNED/RECOVERED headline
  numbers; ~5–10% coverage max.
- `--secondary` (teal `#14B8A6`): supporting chrome, never the primary financial number.
- `--success`: recovered value / approvals / positive deltas; pair with tick-up animation.
- `--destructive`: money at risk, dead stock, margin leakage; MUST be paired with an action control.
- `--warning`: overstock / near-expiry; same action-pair rule.
- Numbers are the visual hierarchy anchor on financial screens (SAR figure largest/boldest).
