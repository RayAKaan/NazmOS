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

test.describe('Owner Journey', () => {
  test('full owner journey: login → dashboard → money-audit → inventory', async ({ page }) => {
    // Step 1: Login
    await loginAs(page, OWNER_EMAIL, OWNER_PASS);

    // Step 2: Dashboard loads
    await expect(page).toHaveURL(/dashboard/);

    // Step 3: Navigate to money-audit
    await page.goto('/money-audit');
    await expect(page.locator('body')).toContainText(/audit|money|risk/i);

    // Step 4: Navigate to inventory
    await page.goto('/inventory');
    await expect(page.locator('body')).toContainText(/inventory|stock|item/i);

    // Step 5: Navigate back to dashboard
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/dashboard/);
  });
});
