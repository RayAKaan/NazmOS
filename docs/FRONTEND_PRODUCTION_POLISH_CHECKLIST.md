# NazmOS Frontend Production-Polish Verification Checklist

This checklist maps each of the 20 "vibecoded website giveaways" to the concrete fix or verification step applied in `/home/user/NazmOS/frontend`.

Validation commands run:

```bash
cd /home/user/NazmOS/frontend
npm run lint      # passes
npm run build     # passes (static prerender of 30 routes)
npm run analyze   # generates .next/analyze/{client,nodejs,edge}.html
```

---

## 1. Vercel.app URL
**Fix / verification**
- Production domain is configured as `https://app.nazm.ai` / `https://nazm.ai`.
- `NEXT_PUBLIC_APP_URL` fallback in `src/app/layout.tsx`, `robots.ts`, `sitemap.ts`, and `structured-data.tsx` points to `https://app.nazm.ai`.

## 2. `view-source:` empty
**Fix / verification**
- Next.js 16 App Router with static generation.
- Verified by opening built `/.next/server/app/login.html`: full `<!DOCTYPE html>` with metadata, body markup, and JSON-LD is present.

## 3. No 404 page
**Fix / verification**
- Created `src/app/not-found.tsx` with on-brand 404 UI, back-home link, and demo link.
- Build output includes `/_not-found` route.

## 4. Vite + React browser defaults
**Fix / verification**
- Stack is Next.js 16 App Router, React 18, TypeScript, Tailwind CSS.
- No Vite config or `index.html` in repo.

## 5. Same page titles
**Fix / verification**
- Every route exports unique metadata:
  - Server routes (`/privacy`, `/terms`, `/demo`) export `metadata` directly from `page.tsx`.
  - Client routes use sibling `layout.tsx` files that export `metadata` and return `children`.
- Title template is `%s | NazmOS` from root layout; root uses default title `NazmOS — Inventory Intelligence OS by Nazmak`.

## 6. No meta description
**Fix / verification**
- Every route has a unique `description` in its metadata.
- Verified in built HTML: `<meta name="description" content="..."/>` appears on `/login`, `/dashboard`, `/product-demo`, etc.

## 7. No `og:image`
**Fix / verification**
- Created `src/app/opengraph-image.tsx` (1200×630) and `src/app/twitter-image.tsx` (1200×600).
- Built HTML contains `<meta property="og:image" content="https://app.nazm.ai/opengraph-image?..."/>` and corresponding Twitter image tags.

## 8. No structured data
**Fix / verification**
- Created `src/components/structured-data.tsx` exporting Organization, SoftwareApplication, and WebSite JSON-LD.
- Injected into root `src/app/layout.tsx` `<head>`.
- Verified in built HTML: three `<script type="application/ld+json">` blocks present.

## 9. Multiple H1 tags
**Fix / verification**
- Audited all `app/` pages and runtime-rendered components.
- Changed logo headings in `src/components/layout/Sidebar.tsx` and `src/components/layout/Logo.tsx` from `<h1>` to `<div>`.
- Each rendered page now contains exactly one semantic `<h1>`.

## 10. No H1 tags
**Fix / verification**
- All public-facing pages and dashboard pages include a single `<h1>` describing the page.

## 11. No canonical tag
**Fix / verification**
- Root layout sets `alternates.canonical: "/"`.
- Every route metadata overrides with route-specific canonical (e.g., `/login`, `/money-audit`, `/settings/autonomy`).
- Verified in built HTML: `<link rel="canonical" href="https://app.nazm.ai/login"/>`.

## 12. No `llms.txt`
**Fix / verification**
- Created `frontend/public/llms.txt` with product, company, domain, capabilities, key pages, stack, and contact info.
- Served at `/llms.txt`.

## 13. AI-blocked `robots.txt`
**Fix / verification**
- Created `src/app/robots.ts` allowing all user agents and pointing to sitemap.
- Built output `/.next/server/app/robots.txt.body` reads:
  ```
  User-Agent: *
  Allow: /

  Sitemap: https://app.nazm.ai/sitemap.xml
  ```

## 14. No favicon
**Fix / verification**
- Created multi-resolution `src/app/favicon.ico` (16×16, 32×32, 48×48) using ImageMagick.
- `src/app/icon.tsx` generates `/icon.png` (512×512) for modern browsers / Apple touch icon.
- Built HTML contains `<link rel="shortcut icon" href="/favicon.ico"/>` and `<link rel="icon" href="/icon.png"/>`.

## 15. No `sitemap.xml`
**Fix / verification**
- Created `src/app/sitemap.ts` covering all 22 static routes.
- Built output `/.next/server/app/sitemap.xml.body` lists every route with `lastmod`, `changefreq`, and `priority`.

## 16. No lang attribution
**Fix / verification**
- Root `src/app/layout.tsx` renders `<html lang="en" dir="ltr">`.
- Verified in built HTML.

## 17. Missing alt text
**Fix / verification**
- No `<img>` tags in `src/`; all imagery is generated via `next/og` or decorative SVG.
- Added `aria-hidden="true"` to decorative SVGs in:
  - `src/components/dashboard/HealthScore.tsx`
  - `src/components/dashboard/KPICardAnimated.tsx`
  - `src/components/free/WhatsAppAlertButton.tsx`
- Landing-page logo SVG already had `aria-hidden="true"`.

## 18. Source maps
**Fix / verification**
- No `.map` files in `/.next/static/` after production build.
- `next.config.js` does not enable production source maps.

## 19. Console errors
**Fix / verification**
- `npm run lint` and `npm run build` pass without warnings or errors.
- Structured-data component is a server component using plain `<script>` tags to avoid hydration mismatch.
- Sidebar logo no longer uses heading level that could trigger a11y warnings in combination with page H1.

## 20. Massive JS bundle
**Fix / verification**
- Added `@next/bundle-analyzer@16.2.10` dev dependency.
- Wrapped `next.config.js` with `withBundleAnalyzer`.
- Added `"analyze": "ANALYZE=true next build --webpack"` script; running it produces `/.next/analyze/client.html`, `nodejs.html`, and `edge.html`.
- `next.config.js` already enables `experimental.optimizePackageImports` for `lucide-react`, `framer-motion`, `recharts`, and `date-fns`.
- Total static chunks after build: ~2.1 MB; largest single chunk ~368 KB (before gzip/brotli).

---

## Files changed / created

### Created
- `frontend/src/app/(auth)/login/layout.tsx`
- `frontend/src/app/(auth)/register/layout.tsx`
- `frontend/src/app/(auth)/onboarding/layout.tsx`
- `frontend/src/app/(dashboard)/dashboard/layout.tsx`
- `frontend/src/app/(dashboard)/inventory/layout.tsx`
- `frontend/src/app/(dashboard)/inventory/expiry/layout.tsx`
- `frontend/src/app/(dashboard)/money-audit/layout.tsx`
- `frontend/src/app/(dashboard)/upload/layout.tsx`
- `frontend/src/app/(dashboard)/feed/layout.tsx`
- `frontend/src/app/(dashboard)/recovery-match/layout.tsx`
- `frontend/src/app/(dashboard)/suppliers/layout.tsx`
- `frontend/src/app/(dashboard)/team/layout.tsx`
- `frontend/src/app/(dashboard)/settings/autonomy/layout.tsx`
- `frontend/src/app/(dashboard)/integrations/layout.tsx`
- `frontend/src/app/(dashboard)/orchestrator/layout.tsx`
- `frontend/src/app/(dashboard)/chain/layout.tsx`
- `frontend/src/app/(dashboard)/ops/layout.tsx`
- `frontend/src/app/product-demo/layout.tsx`
- `frontend/src/app/not-found.tsx`
- `frontend/src/app/robots.ts`
- `frontend/src/app/sitemap.ts`
- `frontend/src/app/favicon.ico`
- `frontend/src/components/structured-data.tsx`
- `frontend/public/llms.txt`
- `frontend/FRONTEND_PRODUCTION_POLISH_CHECKLIST.md` (this file)

### Modified
- `frontend/src/app/layout.tsx` — inject `<StructuredData />` in `<head>`
- `frontend/src/app/terms/page.tsx` — add metadata
- `frontend/src/app/demo/page.tsx` — add metadata
- `frontend/src/components/layout/Sidebar.tsx` — change logo `<h1>` to `<div>`
- `frontend/src/components/layout/Logo.tsx` — change logo `<h1>` to `<div>`
- `frontend/src/components/dashboard/HealthScore.tsx` — add `aria-hidden` to SVG
- `frontend/src/components/dashboard/KPICardAnimated.tsx` — add `aria-hidden` to SVG
- `frontend/src/components/free/WhatsAppAlertButton.tsx` — add `aria-hidden` to SVG
- `frontend/package.json` — add `@next/bundle-analyzer` and `"analyze"` script
- `frontend/next.config.js` — wrap with `withBundleAnalyzer`
