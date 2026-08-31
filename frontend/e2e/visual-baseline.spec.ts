import { test, expect, Page } from "@playwright/test";

/**
 * Visual regression baseline for the NazmOS design-system consolidation.
 *
 * Screenshots every route from docs/FRONTEND_PAGE_MAP.md and stores it under
 *   frontend/e2e/__screenshots__/baseline/<route>.png
 * If a baseline already exists, the same test asserts the live page still
 * matches it (Playwright toHaveScreenshot, no external service).
 *
 * Public routes run without a session (no backend required). Authed dashboard
 * routes rely on e2e/.auth/owner.json, which the `setup` project refreshes by
 * logging in against a running backend — those are captured separately.
 *
 * Run to (re)establish/reset public baselines once the app is served:
 *   npx playwright test visual-baseline --project=chromium --grep "public"
 *
 * A machine/human-readable delta report for any divergence is produced by:
 *   node scripts/visual_delta_report.mjs
 */

const VIEWPORT = { width: 1440, height: 900 };

const PUBLIC_ROUTES: string[] = [
  "/",
  "/product-demo",
  "/login",
  "/register",
  "/terms",
  "/privacy",
];

// Authed dashboard routes (require a running backend + seeded demo data).
const AUTHED_ROUTES: string[] = [
  "/dashboard",
  "/feed",
  "/chat",
  "/orchestrator",
  "/money-audit",
  "/recovery-match",
  "/upload",
  "/inventory",
  "/inventory/expiry",
  "/forecast",
  "/integrations",
  "/ops",
  "/team",
  "/suppliers",
  "/chain",
  "/settings/autonomy",
];

function safeFile(route: string): string {
  return route === "/" ? "index" : route.replace(/^\/+|\/+$/g, "").replace(/\//g, "__");
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.evaluate(() => new Promise((r) => setTimeout(r, 900)));
  await page.evaluate(
    () =>
      (document as Document & { fonts: FontFaceSet }).fonts.ready.then(() => {}),
  );
}

test.describe("Visual baseline: PUBLIC routes", () => {
  test.use({ viewport: VIEWPORT, storageState: { cookies: [], origins: [] } });
  for (const route of PUBLIC_ROUTES) {
    test(`public ${route}`, async ({ page }) => {
      await page.goto(route);
      await settle(page);
      await expect(page).toHaveScreenshot(`${safeFile(route)}.png`, {
        fullPage: true,
        animations: "disabled",
        maxDiffPixelRatio: 0.02,
        timeout: 30000,
      });
    });
  }
});

test.describe("Visual baseline: AUTHED routes", () => {
  test.use({ viewport: VIEWPORT });
  for (const route of AUTHED_ROUTES) {
    test(`authed ${route}`, async ({ page }) => {
      await page.goto(route);
      await settle(page);
      await expect(page).toHaveScreenshot(`${safeFile(route)}.png`, {
        fullPage: false,
        animations: "disabled",
        maxDiffPixelRatio: 0.02,
        timeout: 30000,
      });
    });
  }
});
