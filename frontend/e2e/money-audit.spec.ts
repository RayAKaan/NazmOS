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

test.describe('Money Audit', () => {
  test('money-audit page loads', async ({ page }) => {
    await loginAs(page, OWNER_EMAIL, OWNER_PASS);
    await page.goto('/money-audit');
    await expect(page.locator('body')).toContainText(/audit|money|capital|risk/i);
  });

  test('generate audit button exists', async ({ page }) => {
    await loginAs(page, OWNER_EMAIL, OWNER_PASS);
    await page.goto('/money-audit');
    const btn = page.locator('button:has-text("Generate"), button:has-text("Run"), button:has-text("Analyze")');
    await expect(btn).toBeVisible({ timeout: 10000 });
  });
});
