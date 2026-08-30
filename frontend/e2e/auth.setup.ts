import { test as setup, expect } from '@playwright/test';

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL || 'supermarket_owner@nazmos.sa';
const OWNER_PASS = process.env.E2E_OWNER_PASS || 'Test2026!';
const STATE_FILE = 'e2e/.auth/owner.json';

/**
 * Performs ONE UI login per run and persists the httpOnly session cookie
 * via storageState. This keeps the suite far under the backend's
 * 5-logins-per-5-minutes rate limit.
 */
setup('authenticate as owner', async ({ page }) => {
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').fill(OWNER_EMAIL);
  await page.locator('input[type="password"], input[name="password"]').fill(OWNER_PASS);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/dashboard**', { timeout: 30000 });
  await expect(page).toHaveURL(/dashboard/);
  await page.context().storageState({ path: STATE_FILE });
});
