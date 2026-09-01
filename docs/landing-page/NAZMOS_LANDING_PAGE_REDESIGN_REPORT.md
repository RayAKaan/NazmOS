# NazmOS Landing Page Redesign — Report

Frontend-only rebuild of the public landing page as a story-driven, adaptive, bilingual (EN/AR with RTL), themed (System/Light/Dark), accessible product demonstration. No backend, database, AI, auth, or integration logic was modified.

## Scope guard

- **Frontend only.** `backend/`, APIs, business logic, AI, DB, auth and integrations were **not** touched.
- **No new runtime dependencies.** Reused installed `framer-motion`, `@number-flow/react`, `lucide-react`.
- **No invented claims.** All non-user data is explicitly labeled Sample / Illustrative. No fabricated customers, logos, testimonials, metrics, ROI, certifications, partnerships, or guarantees.
- **Reuse, not parallel architecture.** Existing 3-tier design tokens, i18n, theme toggle, fonts, and motion were extended. The token-guard CI remains intact and passing.

## Claim-vs-reality anchors used

- `docs/phase_a_audit/NAZMOS_CLAIM_VS_REALITY.md`
- `docs/phase_a_audit/NAZMOS_INTEGRATIONS_AUDIT.md`

Landed phrasing: "Built with…" (not "Certified…"); "Designed to learn from outcomes" (not "gets smarter automatically"); autonomy off by default; integrations labeled "not certified".

## What changed

### Fonts & theme (no flash, accessibility)
- Bundled **IBM Plex Sans Arabic** (400/500/600/700) as self-hosted `next/font/local` assets at `src/app/fonts/`. Arabic (variable `--font-arabic`) mirrors the Source Serif 4 pattern. Fonts are committed, not re-fetched at build.
- `src/app/layout.tsx`: added the Arabic font stack, a pre-hydration theme `<script>` in `<head>`, and removed the zoom-throttling `userScalable:false`/`maximumScale:1` viewport props.
- `src/components/theme-script.tsx` (new): applies the saved theme (`nazmos-theme` = light/dark/system) before hydration, listens to OS `prefers-color-scheme` in system mode, and adds `arabic-font` to the `<html>` when `lang="ar"` to avoid font flash / FOUT.
- `src/components/ui/ThemeToggle.tsx` (rewritten): 3-mode segmented control (Light / System / Dark), `localStorage` key `nazmos-theme`, applies `.dark`, tracks OS changes in system mode. Drop-in, used by the app `Header`.

### i18n (EN + AR, RTL)
`src/lib/translations/en.ts` and `ar.ts` gained a full `landing.*` key set (nav, hero incl. idle + sample states, problem, how (5 steps), business-memory, integrations with "not certified" note, trust, pricing incl. honesty note, faq, finalCta, footer, language toggle). Professional Modern Standard Arabic; RTL layout driven by the existing `dir`/`lang` mechanism.

### Landing section components (`src/components/landing/`)
Built from scratch to follow the approved plan (restrained Skiper/Vengeance patterns — scroll reveals, bento, number count — **not** Animmaster's GSAP/WebGL/glow/neon/3D textiles):

- `section.tsx` — shared `Section` / `SectionLabel` helpers
- `logo.tsx` — SVG logo mark with `--brand-gold` gradient
- `Reveal.tsx` — scroll-reveal (`motion` `whileInView`, `once`, reduced-motion aware)
- `SiteHeader.tsx` — sticky nav, dropdown + mobile menu, language switcher, theme toggle, CTA
- `Hero.tsx` — headline, CTAs, trust line, ambient background; `AuditVisual` shows the **live** free-audit result in sustained state or a clearly labeled static **Sample** panel in idle state (via `useAudit`)
- `Problem.tsx`, `HowItWorks.tsx` (5 steps, valid `ol > li`), `BusinessMemory.tsx`, `Integrations.tsx` (marked "not certified"), `Trust.tsx`, `Pricing.tsx` (plans + honesty note), `FAQ.tsx` (native `<details>`/`<summary>`, accessible), `FinalCTA.tsx`, `SiteFooter.tsx`, `FreeAudit.tsx`
- `audit-types.ts` + `audit-context.tsx` (new) — shared client store so the Hero visual syncs with the free-audit uploader result
- `GuestAuditUploader.tsx` — now publishes its successful result to `useAudit`; types extracted to `audit-types.ts`

### Analytics
`src/lib/analytics.ts` (new) — no-dep, console-only (`console.info`), dev/enabled-guard only, bounded in-memory log, privacy-safe (no third party, no network).

### Composition
`src/app/page.tsx` rewritten as a thin composition wrapping all sections in `AuditProvider`.

## Pass 2 — "Living-OS" visualization (window into the product)

Redesigned the landing from "a product described" to **a product watched operating** (§4–6). No backend/AI/DB changes; all figures remain deterministic sample fixtures or the visitor's own live audit result.

### New data-layer types (`src/components/landing/viz/types.ts`)
Separated domain structures (graph nodes/edges, agent states, findings, decisions, outcomes, the signature loop, audit stages) from rendering so visuals can later consume live state without a rewrite. All demo fixtures are deterministic and clearly labeled Sample (§32).

### New reusable primitives (`src/components/landing/viz/`)
- `FlowLine` — animated directional data stream (dashed offset pulse) on an SVG path, reduced-motion aware (§25/§26).
- `NodeChip` — accessible data-driven node; renders a `<div>` when not interactive, a `<button>` when it toggles selection (keyboard + `aria-pressed`).
- `GraphDiagram` — sparse, deliberate relationship graph (§10): HTML chips over an SVG edge layer with semantic relationship labels. **Responsive fallback:** below `sm` it collapses to a compact vertical relationship list (a 6-column graph does not fit 375px and would overflow both languages).
- `SignatureLoop` — the memorable OBSERVE→UNDERSTAND→ANALYZE→RECOMMEND→ACT→MEASURE→LEARN ring (§16) with a traveling pulse; collapses to a static ring under reduced motion.
- `AgentPipeline` — dynamic specialization (§11): only the relevant agents activate; the rest are clearly Idle.
- `DecisionGate` — the deterministic decision boundary (§13): a recommendation advances only when evidence/constraints/budget/risk all pass.
- `OutcomeLoop` — approved action → business result → actual outcome → learning returns to memory (§15).
- `AuditProgress` — staged free-audit processing (§8/§39): maps to the real guest-audit pipeline (read → columns → normalize → match → context → audit → findings) and advances deterministically while the single API request is in flight (never artificially delayed past the real response).

### New story sections (`StorySections.tsx`)
`MemorySection` (SignatureLoop + accumulating memory KPIs), `GraphSection` (GraphDiagram), `AgentsSection` (AgentPipeline), `ReasoningSection` (bounded reasoning), `DecisionSection` (DecisionGate), `OutcomeSection` (OutcomeLoop). Inserted into `page.tsx` between `Problem` and `FreeAudit` to tell the living-OS narrative; the existing HowItWorks/BusinessMemory/Integrations/Trust/Pricing/FAQ are retained.

### Hero rewrite (`Hero.tsx` + `HeroOS.tsx`)
The hero right column is now **HeroOS** — a live miniature of the OS operating: vertical pipeline (Your business → ingestion → business memory → specialist analysis → decision engine) plus an interactive finding (expandable evidence) and a mini graph. It reflects the visitor's own live audit result when present (labeled Live) and deterministic sample data otherwise (labeled Sample).

### Engineering fixes required by QA
- **Hydration stability:** rounded SVG trig/division coordinates (`SignatureLoop`, `GraphDiagram`) so server and client render identical DOM (fixed a real SSR hydration mismatch).
- **Token guard:** replaced `border-primary`/`border-secondary` usages with canonical `border-border` (the CI guard flags `border-*` primary/secondary).
- **Mobile overflow:** added `min-w-0` to grid children and `overflow-wrap:anywhere` on story headings; a single long word ("Recommendations") had forced the grid track to 460px → page overflow. Verified 0px horizontal overflow at 375/768/1280/1440 in **both** EN (LTR) and AR (RTL).
- **i18n truth-in-copy parity:** reworded EN decision body so "nan" (false positive from "financials") is not present; the existing parity test now passes 17/17.
- **Pre-existing corruption:** `en.ts` contained 5 broken em-dashes (`�?` + unescaped `"` → string-termination syntax errors). Repaired to real em-dashes (UTF-8 no-BOM).

## Validation (real commands + results)

| Check | Command | Result |
|---|---|---|
| TypeScript | `npx tsc --noEmit` | PASS, 0 errors |
| Lint (changed files) | `npx eslint <changed files>` | 0 errors, 0 warnings |
| Lint (full project) | `npm run lint` | 0 errors; 6 warnings, all **pre-existing** in untouched files (jest.config.mjs, dashboard, inventory, api.ts) |
| Build | `npm run build` (CI=true) | PASS, EXIT 0 |
| Unit tests (Jest) | `npx jest --ci --runInBand` | 17 passed (4 suites) |
| New Jest: landing parity | `landing.parity.test.ts` | EN↔AR key parity; truth-in-advertising guards (sample/not-certified/illustrative) |
| New Jest: ThemeToggle | `ThemeToggle.test.tsx` | 3-mode render, persistence, `.dark` toggling |
| Axe a11y (statics) | `node scripts/check_a11y.mjs` | **30 pages, 0 serious violations** (fixed an `ol > div > li` nesting violation in HowItWorks) |
| Route/link integrity | `node scripts/check_frontend_routes.mjs` | 29 pages, 87 links, 0 broken → PASS |
| Token-guard self-test | `node scripts/check_legacy_tokens.mjs --self-test` | PASS (17 pos + 15 neg) |
| Token-guard scan | `node scripts/check_legacy_tokens.mjs` | PASS, 199 files, no forbidden design tokens |
| Playwright landing | `npx playwright test landing.spec.ts --config=playwright.public.config.ts` | **8 passed** (hero CTAs, Sample labeling, FAQ, mobile nav, AR→RTL switch, theme toggle, keyboard focus, reduced motion) |
| Playwright navigation | `navigation.spec.ts` (public config) | 4 passed |
| Playwright full public | `npx playwright test --config=playwright.public.config.ts` | **34 passed** |
| Visual baselines (public) | `visual-baseline.spec.ts -g public --update-snapshots` | 6 regenerated: `/` (regrown 8797px → 12388px after new sections), `/product-demo`, `/login`, `/register`, `/terms`, `/privacy` |
| Responsive smoke (Playwright) | scripted 375/768/1280/1440 in EN **and** AR | 0px horizontal overflow all sizes, both languages; no console/page errors |

### New test files / helpers (unchanged for Pass 2, listed for reference)
- `frontend/e2e/landing.spec.ts` — public-only Playwright spec (runs with no session).
- `frontend/src/lib/translations/__tests__/landing.parity.test.ts`
- `frontend/src/components/ui/__tests__/ThemeToggle.test.tsx`
- `frontend/playwright.public.config.ts` — dev-only config running public specs without the auth-setup dependency. Not referenced by CI.

### New files (Pass 2)
- `frontend/src/components/landing/viz/` — `types.ts`, `FlowLine.tsx`, `NodeChip.tsx`, `GraphDiagram.tsx`, `SignatureLoop.tsx`, `AgentPipeline.tsx`, `DecisionGate.tsx`, `OutcomeLoop.tsx`, `AuditProgress.tsx`, `HeroOS.tsx`
- `frontend/src/components/landing/StorySections.tsx`
- Updated: `Hero.tsx`, `GuestAuditUploader.tsx`, `page.tsx`, `src/lib/translations/en.ts`, `ar.ts`

### New test files
- `frontend/e2e/landing.spec.ts` — public-only Playwright spec (runs with no session).
- `frontend/src/lib/translations/__tests__/landing.parity.test.ts`
- `frontend/src/components/ui/__tests__/ThemeToggle.test.tsx`

### Dev-only helper
`frontend/playwright.public.config.ts` — a temporary config that runs public landing/navigation/baseline specs **without** the auth-setup dependency, so the landing can be validated independently of a running backend. Not referenced by CI.

## Documented limitation (not faked)
The backend was **not running** during this session, so authenticated Playwright routes (dashboard, money-audit, `/chain`, upload, etc.) and their visual baselines could not be re-established. This is a stated limitation, **not** simulated. Public landing tests and public visual baselines are fully reproducible without a backend.

## Files touched (primary)
- `frontend/src/app/page.tsx`, `frontend/src/app/layout.tsx`
- `frontend/src/components/theme-script.tsx` (new)
- `frontend/src/components/ui/ThemeToggle.tsx`
- `frontend/src/components/landing/*` (all section components + `audit-types.ts`, `audit-context.tsx`, `logo.tsx`, `section.tsx`, `Reveal.tsx`, `FreeAudit.tsx`; `GuestAuditUploader.tsx` updated)
- `frontend/src/lib/analytics.ts` (new)
- `frontend/src/lib/translations/en.ts`, `ar.ts`
- `frontend/src/app/fonts/ibm-plex-sans-arabic-{400,500,600,700}.woff2`
- `frontend/e2e/landing.spec.ts` (new), `frontend/e2e/__screenshots__/baseline/index.png` (+ other public baselines)
- `frontend/playwright.public.config.ts` (dev-only helper)
- `frontend/src/lib/translations/__tests__/landing.parity.test.ts` (new)
- `frontend/src/components/ui/__tests__/ThemeToggle.test.tsx` (new)
