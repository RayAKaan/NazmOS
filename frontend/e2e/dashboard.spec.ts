import { test, expect } from '@playwright/test';

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL || 'supermarket_owner@nazmos.sa';
const OWNER_PASS = process.env.E2E_OWNER_PASS || 'Test2026!';

async function loginAs(page: any, email: string, password: string) {
  // Reuse the storageState session when present; only fall back to a UI
  // login when unauthenticated (keeps us under auth rate limits).
  await page.goto('/dashboard');
  if (!page.url().includes('/login')) return;
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').fill(email);
  await page.locator('input[type="password"], input[name="password"]').fill(password);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/dashboard**', { timeout: 30000 });
}

test.describe('Dashboard (authenticated)', () => {
  test('dashboard loads with KPIs', async ({ page }) => {
    await loginAs(page, OWNER_EMAIL, OWNER_PASS);
    await expect(page.locator('body')).toContainText(/dashboard|kpi|revenue|inventory/i);
  });

  test('sidebar navigation links exist', async ({ page }) => {
    await loginAs(page, OWNER_EMAIL, OWNER_PASS);
    // Multiple nav elements exist (sidebar, header, mobile); assert the
    // sidebar aside contains navigation links without strict-mode ambiguity.
    const sidebarLinks = page.locator('aside nav a');
    await expect(sidebarLinks.first()).toBeVisible({ timeout: 15000 });
    expect(await sidebarLinks.count()).toBeGreaterThanOrEqual(5);
  });
});
