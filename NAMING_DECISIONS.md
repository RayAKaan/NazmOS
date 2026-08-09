# NAMING_DECISIONS

Decisions that need **founder sign-off** before they ship. Nothing here has been changed unilaterally. The audit evidence for each is attached.

Status legend: 🔶 needs sign-off · ✅ decided this audit (no further action)

---

## 1. 🔶 "Orchestrator" (Recovery Engine) vs "Recovery Match" — naming overlap

**Symptom (evidence):**
- `Sidebar.tsx:22` — `/orchestrator` fallback label `"Recovery Engine"` (no translation key; `t.sidebar.orchestrator` does not exist in `en.ts`/`ar.ts`).
- `Sidebar.tsx:27` — `/recovery-match` label `"Recovery Match"`.
- Two different tools both carrying the word "Recovery" in a 6-item nav is confusing for merchants.
- Badge audit also flagged orchestrator's `"Recovery"` badge as redundant; **fixed** this audit to `"Pilot"` (tier-parity with ops/`Founder`).

**Where the naming is in tension:**
- **Recovery Engine (orchestrator):** agent orchestration, approvals, autonomous replenishment. Pilot-tier.
- **Recovery Match:** manual surplus-listing / match / recover marketplace. Preview-tier.
- The free/recovery funnel (`/product-demo`, `/money-audit`, `FeatureGate.tsx:17` "Recovery Pilot") uses "recovery" as the *product* verb, so the collision is systemic.

**Recommendation (choose one, founder):**
1. **Rename orchestrator → "Agent Ops" / "Pilot Orchestration"** (keeps "recovery" for the merchant-facing funnel, "pilot" for the internal engine). *(Recommended — smallest diff: one label + sidebar key.)*
2. Keep "Recovery Engine" but ship a real `t.sidebar.orchestrator` translation and make badges tier-only (done) — accept the overlap.
3. Fold orchestrator into `/ops` until it earns its own name.

**Not done this audit:** label rename, translation key. Only the badge changed (`Recovery` → `Pilot`).

---

## 2. 🔶 First-run path: should post-register go straight to Money Audit?

**Current path (script-traced):**
`/register` → `/onboarding` (4-step zero-API wizard) → `/dashboard` → Money Audit empty state + "Upload files" CTA.

**Finding:** onboarding never calls the API and never creates a business; `/dashboard` then shows the Money Audit empty state as its hero. The "First user job" guidance (`MoneyAuditEmptyState.tsx:17`) explicitly says *"The first screen should not make you learn software — it should help you find recoverable cash."* Today a fresh merchant must traverse onboarding → dashboard before reaching that message, and there is **no redirect**; the empty-state CTA is their only path.

**Recommendation (choose one, founder):**
1. **Post-register redirect to `/money-audit`** (or a first-run `/money-audit` variant) with the empty state + upload CTA as the landing, skipping dashboard on first run. *(Recommended — matches the stated first-user-job principle.)*
2. Keep current flow but shrink onboarding to 1 step and make `/dashboard` a thin redirect to `/money-audit` while business is empty.
3. Leave as-is.

**Not done this audit:** no silent redirect added (founder decision required — the brief forbade unilateral redirect changes).

---

## 3. 🔶 Server-side auth surface gap

**Finding (evidence):** `middleware.ts:4-16` `PROTECTED_SEGMENTS` omits `inventory`, `inventory/expiry`, `forecast`, `chat`, `suppliers`. These pages depend on the client-only `(dashboard)/layout.tsx` guard: unauthenticated users get a browser-side redirect instead of a server 307, and the page HTML is served before the guard runs.

**Recommendation:** add the five segments to `PROTECTED_SEGMENTS` so server and client guards match. Low risk; changes auth posture so it needs sign-off, not a silent fix.

---

## 4. ✅ Decided this audit (no sign-off needed)

| Decision | Evidence | Change |
|---|---|---|
| Build `/forecast` page (not remove nav) | backend `forecast.py` + `types/forecast.ts` already existed; sidebar linked it | new `(dashboard)/forecast/page.tsx` |
| `/demo` → `/product-demo` permanent 301 | was a 307; two demo pages redundant | `permanentRedirect` |
| Bootstrap race: **both** frontend lock + backend unique index/upsert | layout had no in-flight lock; backend select-then-insert | ref lock + `uq_businesses_active_owner` + `ON CONFLICT DO NOTHING` (migration `5f0a1b2c3d4e`) |
| Mobile nav: add "More" sheet (not prune) | MobileNav 5 items vs Sidebar 11+ | bottom-sheet parity + i18n keys |
| Orchestrator badge `Recovery` → `Pilot` | redundant with label, collided with Recovery Match | Sidebar.tsx:22 |
| Design tokens: document, don't blind-replace | 614 hex usages / 956 arbitrary utilities | documented in `FRONTEND_PAGE_MAP.md` #12 |
