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

test.describe('Upload', () => {
  test('upload page loads', async ({ page }) => {
    await loginAs(page, OWNER_EMAIL, OWNER_PASS);
    await page.goto('/upload');
    await expect(page.locator('body')).toContainText(/upload|file|import|csv/i);
  });

  test('file input exists on upload page', async ({ page }) => {
    await loginAs(page, OWNER_EMAIL, OWNER_PASS);
    await page.goto('/upload');
    // The drag-drop pattern keeps the input visually hidden; assert it is
    // attached and the dropzone is interactive.
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toHaveCount(1, { timeout: 15000 });
    await expect(page.locator('text=Drop a sales or inventory file here')).toBeVisible();
  });
});
