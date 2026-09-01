# NazmOS Landing Rebuild — Design Plan (Pass 3: Template → Signature)

Status: **ready for review before coding** (Phase 2 gate).
Companion asset decision: **Phase 1 — asset inventory incomplete; flagged for user input below.**

---

## 0. Phase 1 — Asset inventory (real findings)

| Asset needed | Status |
|---|---|
| Brag render / cinematic stills (aerial Riyadh + Recovery Match arcs, pharmacy shelf, glass architecture) | **NOT FINDABLE.** No `*.mp4`/`mov`/`webm` anywhere in the workspace, user home, Downloads, Videos, Documents, Desktop, or Temp. No `Hyperframes`/`Remotion` output dir exists. |
| `frontend/public/marketing/*` | **Does not exist.** `public/` holds only `llms.txt`, `manifest.json`, `sw.js`. Zero imagery on the page today. |
| Alternative stills | Candidate PNGs exist in `C:\Users\Rayyan Khan\Downloads` (several "ChatGPT Image" renders dated Sep 1 2026 + `System_Architecture_Diagram.png`). **Cannot verify contents** — this model has no image input. |
| Real product screenshots | Backend not running → cannot capture authed Money Audit / WhatsApp approval screens. The public `/product-demo` simulator exists but I cannot screenshot-and-view it either. |
| WhatsApp approval mockup on the landing | **Does not exist.** It is a real in-product behavior (approve recovery actions on WhatsApp) — will be *added* as an authentic phone mockup, not a replacement. |
| Licensing | Own assets assumed (user-generated renders). If stills are AI-image-service output, user must confirm commercial terms before we ship them. **Unresolved — user sign-off required.** |

**Decision required from the user (blocking Phase 3's image slots):**
1. Provide the path to the brag render / marketing stills, OR
2. Authorize using specific Downloads files (describe which = hero plate, which = featured-card plate), OR
3. Authorize image-less build: the two "image" moments use rich CSS/SVG treatments (gradient ground, woven arc motif — see §5), with `<Image>` slots wired so photos can be dropped into `frontend/public/marketing/` later with zero code change.

---

## 1. Diagnosis (verified against current code, not assumed)

Confirmed tells in `frontend/src/app/page.tsx` + components today:

- **SectionLabel eyebrow above every section** — used in **9 places**: Problem, Memory/Graph/Agents/Reasoning/Decision/Outcome (via `StoryHeader`), FreeAudit, HowItWorks, BusinessMemory, Integrations, Trust, Pricing, FAQ. Identical `font-mono uppercase tracking-[0.28em]` every time.
- **Reflexive arrow on CTAs**: hero primary CTA, FinalCTA, SiteHeader (2), GuestAuditUploader (2).
- **Uniform card kit**: `rounded-3xl border border-border bg-card shadow-elevation-1` repeated across Problem (4-up), HowItWorks (list), BusinessMemory, Integrations (grid), Trust (3-up), Pricing (3-up), FAQ (`details`). Same radius, same border, same `shadow-elevation-1`, same interior.
- **`font-mono uppercase tracking-[0.2em+]` decoration** on nearly every label (`SectionLabel`, hero pill `tracking-[0.2em]`, viz micro-labels) — used decoratively, not because the content is tabular.
- **Zero imagery** — 100% typography + lucide line icons on flat color.
- **Two backgrounds, one accent rhythm**: `bg-muted/30` alternates with default background; single `accent-primary`/`success` accent; the ~17 `brand-*` primitives are unused on the landing except inside `GuestAuditUploader`.
- **Every headline identical**: `font-serif ... font-black ... leading-tight tracking-[-0.02em]` — only the size (`text-4xl`→`md:text-6xl`) varies. No weight contrast, no color contrast.

Rule applied for this pass: *spend the boldness in a few signature moments; stay disciplined everywhere else.*

---

## 2. COLOR — one moment per accent (this is a rhythm system, not a palette)

Each non-amber accent gets exactly **one** section where it is the hero color and appears nowhere else on the page.

| Section | Dominant color | Why / where |
|---|---|---|
| Hero | `--brand-night` ground + photo plate (or §5 fallback) | The dark ground is the product's world. |
| Problem / "Four ways stores lose money" | **`--brand-red`** (+ `brand-red-light` for the `01` numeral) | Risk/urgency moment. Used nowhere else. |
| Story sections (Memory→Outcome, viz) | semantic neutral (`bg-card` etc.) | Stay quiet; the OS visualizations are the accent. |
| FreeAudit | neutral + `brand-cream` on the fixed-dark result panel | The audit result panel is the object. |
| HowItWorks | neutral | Quiet connective tissue. |
| BusinessMemory | `--brand-gold` bleeding mark (one-company panel) | The company memory beat. |
| Integrations | neutral + `whatsapp`/`warning` already present | Unchanged structurally (already honest/labelled). |
| Trust → **Recovery Match** | **`--brand-teal`** + gradient to `oklch(18% 0.02 190)` | The network/verification moment — the product already uses teal for exactly this. One-time teal use. |
| Pricing | neutral; primary CTA row kept equal-grid (decision §4) | Comparison needs equal weight — but the top card CTA is amber. |
| FinalCTA | semantic, subtle | Close without shouting. |
| **Primary CTAs** (hero, FreeAudit, FinalCTA) | **`--brand-amber` on `--brand-night` text** (`bg-brand-amber text-brand-night`) | Amber is *reserved* for the one critical action — not decorative labels. |

Explicit constraint: `brand-amber` appears **only** as CTA fill + the small gold mark in BusinessMemory (that mark uses `--brand-gold`, distinct). `brand-teal` appears only in Trust/Recovery-Match. `brand-red` only in Problem. `brand-green` only in the "money recovered" proof moment (OutcomeSection loop footer + FinalCTA note if needed).

This kills the two-tone loop: a reader passes through night → red-risk → neutral-story → gold-memory → teal-network → neutral-pricing instead of one repeating pair.

---

## 3. TYPE — intra-headline weight contrast (≥3 headlines)

Keep `font-serif` (Source Serif 4). New rule: **at least three headlines use a structural light/black weight system across the whole headline** (not a single bolded punch word — the skill flags that separately). Rendered values are Tailwind `font-extralight` ↔ `font-black`; in RTL they mirror automatically.

Specific headlines (mapped to real copy):

1. **Problem** (rebuild):
   `<h2>` → "**Four ways** stores lose money *quietly.*"
   - `font-serif text-4xl md:text-5xl leading-[0.95] tracking-[-0.02em]`
   - `<span font-extralight text-muted-foreground>Four ways</span> <span font-black text-foreground>stores lose money</span> <span font-extralight text-muted-foreground>quietly.</span>`
2. **Recovery Match (Trust)** — teal moment:
   "A branch that *has it* meets a branch that needs it."
   - light `has it` / black `meets a branch that needs it.`
3. **BusinessMemory** (one-company panel):
   "Built by **Nazmak** — for stores like *yours.*" (weight contrast across company/product names)
4. (Reserve) **FinalCTA** may borrow the pattern if the first three render well.

All other headlines drop to a **single** weight (`font-bold`, not `font-black`) with `text-3xl md:text-4xl`, so the contrasting ones read as moments, not wallpaper. `font-black` is *spent*, not spread.

`SectionLabel` usage: cut from 9 → **3** (FreeAudit keeps one centered; Pricing keeps one centered; StoryHeader keeps its `StoryHeader` treatment). Problem, HowItWorks, BusinessMemory, Integrations, Trust/RecoveryMatch, FAQ **lose the eyebrow** — those sections open directly on the headline (which now carries contrast). The eyebrow's mono-uppercase energy is preserved only where content is genuinely step/data (Pricing keeps mono "01/02/03" card numbers; viz micro-labels stay).

---

## 4. LAYOUT — three deliberate breaks from the card kit

### 4a. Problem → asymmetric editorial, red moment (was: 4-up equal grid)

```
┌───────────────────────────────┬───────────────┐
│                               │ 02 Stockouts  │
│   01 CASH LEAKAGE             ├───────────────┤
│   [image plate / red arc]     │ 03 Margin     │
│   large serif + real numbers  │               │
│   (dead stock · trapped cash) ├───────────────┤
│   numeral 01 in brand-red     │ 04 Branch     │
│                               │  │            │
└───────────────────────────────┴───────────────┘
```
- Featured tile spans `md:col-span-2 md:row-span-2`, is **`brand-red`** coloured (the one-time red moment), carries the `01` numeral + a real audit-shaped number ("Cash trapped: SAR X in dead stock") taken from the *sample* audit figures — labelled Sample, per truth rules.
- Background: if a pharmacy-shelf still is provided → `<Image fill object-cover>` + `bg-gradient-to-t from-brand-night via-brand-night/70` scrim + red numeral. If not → a **red baked-glass weave + arc motif** (SVG `WeaveTile` reuse, §5 fallback) with the same layout weight.
- The other three items are **deliberately quieter** — plain bordered rows, smaller serif, no icon chip, no hover-lift — they are the supporting cast to the featured tile, not another row of identical cells.

### 4b. Pricing — the one place the equal 3-up grid is the RIGHT choice (explicit decision)
Comparison genuinely benefits from equal visual weight: three plans, same shape, same hierarchy, only the middle (Pilot) gets a subtle `border-brand-amber/40` ring and an amber CTA. This is a *decision*, not a leftover habit — stated here so reviewers read it as intentional.

### 4c. BusinessMemory → one-company continuous panel (was: separate object card)
Nazmak and NazmOS share one full-width split panel: a single `bg-card` surface, the **gold mark bleeding across both halves** (one SVG `logoMark` positioned so its glow crosses the split), left half = "NazmOS — the Retail Recovery System", right half = memory points. No two bordered boxes arguing they're unrelated.

### 4d. NEW — WhatsApp owner-approval phone mockup (authentic, added)
The product's real behavior: *recovery actions arrive as owner approvals on WhatsApp*. Build `PhoneFrame` (chassis `round-[2.75rem]` metal-grey gradient → black → `bg-brand-cream` screen) + `ChatBubble` (`in`/`out`, tailed side `rounded-bl-sm`/`rounded-br-sm`) per the brief, placed as the OutcomeSection's right rail alongside `OutcomeLoop`: bubble thread = Money Audit result → "Recover 3,140 SAR?" → `Approve` reply, then the loop's "returns to memory" note. Uses `bg-chat-steel`/`bg-whatsapp` tokens (already in the design system). This converts a flat viz beat into the "owner approves from their pocket" proof — honest, and reuses the WhatsApp callout that already exists in the product.

### 4e. Hero → cinematic plate (keeps SplitText *and* HeroOS)
Full-bleed `<Image>` plate (aerial Riyadh + Recovery Match arcs) OR the §5 vector fallback, double scrim (`to-t from-brand-night …` + `to-r` legibility), `AmbientBackground` dropped to ~40% opacity as a secondary accent, content **left-aligned in the lower third** (`items-end pb-20`), SplitText headline retained, **HeroOS retained** as the product window floating over the dark scrim (it is Pass-2's signature — removing it contradicts "window into the product"). Only the hero primary CTA keeps an arrow (§7).

---

## 5. Image fallback doctrine (used only if assets stay unavailable)

No AI/diffusion generation — per brief. For each image slot, render a **procedural SVG/CSS plate** instead (SVG+CSS is the sanctioned rich-render path in this repo):
- **Hero**: full-bleed `brand-night` → `brand-teal-dark` radial aurora at low opacity + a woven arc motif (reuse `WeaveTile` sprite) reading as the Riyadh skyline, plus thin gold/teal Recovery-Match arcs connecting manufactured "store nodes" (two glow arcs only — they visualise the product concept, not a fake map).
- **Problem featured**: a red-on-night baked weave with a soft arc; the tile still carries real structure (numeral, headline, sample number).
- Slots are componentised as `HeroPlate` / `FeaturedPlate` exporting the `<Image>` branch; dropping files at `frontend/public/marketing/hero-riyadh-aerial.jpg` and `frontend/public/marketing/pharmacy-shelf.jpg` is a zero-code swap.

---

## 6. Social-proof / truth decision (flagged for sign-off, not decided silently)

- The **fictional-store marquee does not exist** in current code, so nothing is removed — but the brief's honesty call IS honoured: no fake customer names, logos, or testimonials are introduced anywhere.
- **Trust section is reframed as "Recovery Match" — a concept, not a claim of existing customers:** "The kind of stores we're built for — nearby branches trading surplus against shortage." The section is **teal**, demonstrates the cross-branch trade idea with two labelled store tiles (Branch A / Branch B), and carries the existing "Product truth" line. No invented store names appear.
- New sample numbers (featured cash-leakage figure) are labelled **Sample** and traceable to the deterministic fixtures already in `viz/types.ts`.
- **User sign-off requested** on: (a) the Recovery-Match-as-concept framing, (b) any use of the unverifiable Downloads images, (c) the WhatsApp approval mockup representing a real (if pilot-stage) feature.

---

## 7. CTA discipline — exactly one arrow on the page

- **Hero primary CTA**: keeps `ArrowRight` (`ArrowLeft` in RTL) — it is the single most important action.
- **All other CTAs lose the arrow**: FinalCTA ("Get a Free Money Audit" — plain), SiteHeader "Get Started" + "Run the demo", GuestAuditUploader CTAs, Pricing CTAs. Hover affordance = color/underline shift, not a directional icon.
- This makes the remaining arrow *mean* something again.

---

## 8. Section-by-section build order (Phase 3)

1. `HeroPlate` + `FeaturedPlate` (image-or-fallback) primitives.
2. Hero rewrite (image-backed, SplitText retained, HeroOS floating, amber CTA, arrow kept).
3. Problem rewrite (asymmetric editorial, red moment, weight-contrast headline `Four ways … quietly.`).
4. `PhoneFrame` + `ChatBubble` primitives; wire WhatsApp approval rail into OutcomeSection.
5. Trust → Recovery Match (teal, concept tiles, no fake names; headline #2 weight contrast).
6. BusinessMemory → one-company gold split panel (headline #3 weight contrast).
7. Pricing: keep equal grid; amber ring/CTA on middle; remove stray arrows.
8. FinalCTA: remove arrow; SectionLabel cuts (9 → 3).
9. CTA audit: `grep` for `ArrowRight`/`ArrowLeft` — must end with exactly 1 functional arrow (hero primary) + 0 elsewhere on landing (header nav arrows e.g. mobile menu chevrons are fine, they are not CTAs).
10. EN + AR copy parity for all new strings (Problem featured, Recovery Match, WhatsApp thread, BusinessMemory split, any headline fragments). Reuse existing keys; add only necessary ones; keep `landing.parity.test.ts` green (avoid the substring "nan"; reuse "Sample"/"Illustrative" labels).

Declared unchanged (out of brief scope / already deliberate): Story viz sections (they are Pass-2's signature and already use semantic tokens + micro-labels), FAQ (structure is fine), Integrations (already honest/labelled), FreeAudit's deterministic uploader behavior.

---

## 9. Critique pass (against the plan above — written down, not skipped)

For each move I asked: *"would I produce this for any generic B2B SaaS brief?"* and corrected where the answer was yes.

- **Four-ways editorial bento** → could read as a generic "features bento". Fix: the featured item is not a feature, it is the **`01` red-cash moment with a real sample figure** (money trapped, labelled Sample) — it sells the *specific* Saudi-retail pain the product already measures (dead stock / stockout / margin / branch imbalance are the product's own categories, not invented pillars).
- **"One accent one section"** → is itself a rule generic SaaS would copy. Fix: the accent assignment is derived from *where the product already uses those colors* (teal = verification/network in-product; red = risk states; green = recovery). We are not inventing a palette, we are surfacing the product's existing one. Stated so reviewers can check.
- **Weight-contrast headlines** → the risk is it becomes the new uniform treatment. Fix: capped at 3; the other ~6 drop to single-weight `font-bold` and smaller so contrast stays a rarity. Also every contrasted headline is constructed from the actual copy, light/black is chosen to mirror meaning (could-be-fine vs. is-wrong), not random emphasis.
- **Keep HeroOS in an image hero** → risk: hero gets busy (image + scrim + viz + headline). Fix: HeroOS sits behind a slightly stronger scrim and is **not animated-in** the same way (`initial=false`); it behaves as a window, not a decoration, and it is the Pass-2 product signature the brief's own frame ("window into the product") demands.
- **Amber on all primary CTAs** → risk of amber being everywhere again. Fix: amber fill on the hero primary + the *middle* pricing card only; FinalCTA stays semantic `bg-primary`. Two amber moments total.
- **Pricing keeps the grid** → I verified this is the *only* section where equal weight is a comparison benefit, not a laziness marker, and said so explicitly rather than silently reusing the card kit.

---

## 10. Validation plan (reuse the existing guard suite, do not weaken it)

- `npx tsc --noEmit` — 0 errors.
- `npm run build` (CI=true) — EXIT 0.
- `npm run lint` — 0 errors (existing 6 warnings are pre-existing, untouched).
- `node scripts/check_legacy_tokens.mjs` — PASS (only `border-*` primary/secondary banned; `brand-*` is legal — verified).
- `node scripts/check_a11y.mjs` — 30 pages, 0 serious (colour-contrast rule already tracked separately by design).
- `node scripts/check_frontend_routes.mjs` — PASS.
- `npx jest --ci --runInBand` — 17 passing incl. `landing.parity.test.ts` (EN↔AR parity + truth-in-advertising).
- `npx playwright test --config=playwright.public.config.ts` — 34 passing; re-check `landing.spec.ts` assertions (hero CTA href, FAQ, mobile nav, Sample labelling, theme, reduced-motion) and **regenerate `/index.png` baseline**.
- New Post-build check: `rg -n "ArrowRight|ArrowLeft"` over `src/components/landing` → only hero primary CTA (and header's mobile-menu arrows/guest-audit internals per declared exclusions).
- Responsive: Playwright overflow probes at 320/375/640/768/1280/1440, EN + AR (inherits Pass-2 overflow doctrine: `min-w-0`, `overflow-wrap-anywhere`, phone mockup max-width guard).

---

## 11. Deliverables after build (Phase 4)

- `docs/landing-page/LANDING_REDESIGN_REPORT.md` — before/after screenshots (I cannot view them; will produce the artifacts and note this limitation), asset list + provenance (brag.mp4 extract vs. procedural CSS vs. existing icon), and the explicit §6 social-proof decision for sign-off.
- Commit + push to `origin/main` only after all validation green (per repo workflow).

---

## Blocking questions (Phase 1 → Phase 3 gate)

1. **Assets**: provide render path / confirm Downloads files (which = hero, which = featured) / or authorise image-less procedural fallback with photo-ready slots?
2. **Sign-off** on: Recovery-Match-as-concept (§6), amber-two-moments (§2/§9), WhatsApp approval mockup (§4d), weight-contrast headine x3 (§3)?
3. Confirm the plan (any sections you want reworded before I build)?