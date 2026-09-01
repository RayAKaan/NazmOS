# NazmOS Landing Rebuild — Report (Pass 3: From Template to Signature)

Status: **shipped and validated.** Companion plan: `LANDING_REDESIGN_PLAN.md` (reviewed + approved before coding).

---

## 1. What changed (template → signature)

Diagnosed each generic-AI tell in the current code, then removed or converted it:

| Tell (before) | After | File |
|---|---|---|
| `SectionLabel` eyebrow above **9** sections | Kept on **3** (FreeAudit, Pricing, + StoryHeader); removed from Problem, HowItWorks, BusinessMemory, Integrations, FAQ — those now open straight on the headline | `section.tsx` callers |
| Reflexive arrow on every CTA | **One arrow** on the page (hero primary CTA); removed from FinalCTA, SiteHeader (2), GuestAuditUploader (2). Recovery-Match uses a symmetric `ArrowLeftRight` exchange glyph (diagram, not CTA). | Hero / FinalCTA / SiteHeader / GuestAuditUploader |
| Uniform `rounded-3xl border-card shadow` kit across all sections | **Four distinct layouts**: asymmetric red editorial (Problem), full-width gold split panel (BusinessMemory), teal exchange grid (RecoveryMatch), 3-up equal grid (Pricing, kept deliberately) | Problem / BusinessMemory / RecoveryMatch |
| Identical `font-serif font-black` headline everywhere | **3 weight-contrast headlines** (Problem `Four ways *stores lose money* quietly.`, RecoveryMatch `A branch that has it *meets a branch that needs it.*`, BusinessMemory `Built by **Nazmak** — for stores like yours.`); the other ~6 dropped to single-weight `text-3xl/4xl font-bold` so contrast stays a rarity | Problem / RecoveryMatch / BusinessMemory / StoryHeader / others |
| Mono-uppercase `tracking-[0.2em+]` decoration on labels | Preserved only where content is genuinely step/data (Pricing card numbers, viz micro-labels, sample chips) — not as page-wide eyebrows | Pricing / viz / Sample chips |
| **Zero imagery**, 2 flat backgrounds | **Two signature image-backed slots** (Hero plate, Problem featured tile) via procedural CSS/SVG plates with drop-in photo slots; richer background rhythm | `viz/HeroPlate`, `viz/FeaturedPlate` |
| 2 backgrounds, one accent | **One-accent-one-section rhythm**: brand-red only in Problem · brand-teal only in RecoveryMatch · brand-gold only in BusinessMemory mark · amber only on hero-primary + middle pricing CTA | throughout |

### New signature moments (all additive / honest)
- **Problem → `01 Cash leakage`**: brand-red image-backed editorial tile with a Sample cash figure (SAR 27,400) + three deliberately quieter supporting rows (Stockouts · Margin · Branch). The four "ways stores lose money" are the product's own categories, not invented pillars.
- **RecoveryMatch (was Trust)**: teal concept section "A branch that has it meets a branch that needs it" — two labelled Branch A/B tiles exchanging surplus against shortage. **No invented customer names, logos, or testimonials.** The existing "Product truth" points ride beneath. Trust section replaced; nothing fictional introduced.
- **ApprovalPhone (WhatsApp)**: real product behavior made visible — recovery actions arrive as owner approvals. New `PhoneFrame`-style chassis dark chrome + WhatsApp bubbles added to the Outcome section's right rail. Transliterated for EN + AR.
- **BusinessMemory → one-company panel**: Nazmak and NazmOS now share one continuous gold-bleeding surface (the logo glow crosses the split) with the weight-contrast headline. One company, one panel — not two unrelated boxes.

---

## 2. Assets list
Since no brag-render / marketing stills exist on this machine and the model cannot view images to verify candidates, the build is **image-less with procedural plates + photo-ready slots** (per approved decision):

| Slot | Current art (procedural) | Swap-in (zero code change) |
|---|---|---|
| Hero plate | brand-night aurora + gold/teal Recovery-Match arcs + weave + regatta grid | `frontend/public/marketing/hero-riyadh-aerial.jpg` |
| Problem featured tile | brand-red aurora + shelf-light flecks | `frontend/public/marketing/pharmacy-shelf.jpg` |

No videos, fonts, or third-party assets were added. All imagery is CSS/SVG + design tokens (guard-compliant). Licensing: none introduced (no downloaded assets shipped).

---

## 3. Social-proof / truth sign-off (honesty wording)

- **No fake customers, logos, or testimonials** anywhere. The previous `Trust` section already had none (its "fictional store marquee" never existed in code) — nothing was removed, and nothing fictional was added.
- New sample figures are **labelled Sample / Illustrative** and trace to the existing deterministic fixtures (`viz/types.ts`: `SAMPLE_FINDINGS.estimatedValue` = 27,400; `SAMPLE_DECISION.value` = 8,600). The WhatsApp thread is labelled "Sample thread".
- RecoveryMatch is framed as **a concept** ("the kind of stores we're built for... a real mechanism the paid pilot delivers"), not as existing customers.
- Trade-labelled as: ✅ agreed.

---

## 4. Files touched

**New:** `src/components/landing/{ApprovalPhone,RecoveryMatch}.tsx`, `src/components/landing/viz/{HeroPlate,FeaturedPlate}.tsx`, `scripts/overflow_probe.mjs`, `scripts/capture_redesign_shots.mjs`.
**Edited:** `Hero.tsx`, `Problem.tsx`, `BusinessMemory.tsx`, `StorySections.tsx` (headings + WhatsApp rail), `FinalCTA.tsx`, `SiteHeader.tsx`, `GuestAuditUploader.tsx`, `Pricing.tsx`, `HowItWorks.tsx`, `Integrations.tsx`, `FAQ.tsx`, `FreeAudit.tsx`, `section.tsx` (unchanged), `app/page.tsx`, `lib/translations/{en,ar}.ts`.

---

## 5. Validation (all guards green)

| Check | Result |
|---|---|
| `npx tsc --noEmit` | PASS (0 errors) |
| `npm run build` (CI=true) | PASS (38/38 pages) |
| `npx eslint .` | 0 errors (6 pre-existing warnings, untouched baseline) |
| `scripts/check_legacy_tokens.mjs` | PASS (204 files) |
| `scripts/check_a11y.mjs` | PASS — 30 pages, 0 serious |
| `scripts/check_frontend_routes.mjs` | PASS — 0 broken, 6 justified-orphaned |
| `npx jest --ci --runInBand` | 17/17 (incl. `landing.parity.test.ts` EN↔AR + truth guards) |
| Playwright public (`playwright.public.config.ts`) | **34/34** (incl. 7 functional `landing.spec` + visual baselines, `/` baseline regenerated) |
| Overflow probe | 0px overflow at 320/375/640/768, EN + AR |

---

## 6. Before / after (screenshots — **user-verified**, model has no image input)

Captured full-page renders of the final build:
- `docs/landing-page/redesign-shots/home-full-final.png` (light, desktop)
- `docs/landing-page/redesign-shots/home-dark-final.png` (dark, desktop)
- `docs/landing-page/redesign-shots/home-mobile-final.png` (mobile 390px)
- `docs/landing-page/redesign-shots/home-ar-final.png` (Arabic/RTL)

I cannot visually confirm these images — **please open and sign them off** (hero composition, WhatsApp phone chrome, teal Recovery-Match, red Problem tile, gold BusinessMemory split, weight-contrast headlines).

---

## 7. Notes / residual decisions for the user
- Keep `HeroOS` + SplitText in the image hero (approved): it is Pass 2's product signature and reads as "a window into the product" over the plate.
- Amber appears exactly twice (hero-primary CTA + middle Pricing card CTA). Pricing keeps the equal 3-up grid as a deliberate comparison choice.
- `SectionLabel` mono eyebrows are down to 3 (plus the StoryHeader treatment which mirrors it) — the visual consolidation is the *absence* of the tell, not its spread.