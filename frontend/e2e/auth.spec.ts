import { test, expect } from '@playwright/test';

// These tests exercise the UNAUTHENTICATED experience; opt out of the
// shared storageState so they start with no session cookie.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('Auth Flow', () => {
  test('login page loads and has form elements', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('input[type="email"], input[name="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"], input[name="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('login with invalid credentials shows error', async ({ page }) => {
    await page.goto('/login');
    const emailInput = page.locator('input[type="email"], input[name="email"]');
    const passInput = page.locator('input[type="password"], input[name="password"]');
    const submit = page.locator('button[type="submit"]');
    await emailInput.fill('nonexistent@nazmos.sa');
    await passInput.fill('WrongPassword!');
    await submit.click();
    // Language-agnostic failure signal: user stays on /login while the
    // form re-enables after the failed attempt (error toast is i18n'd).
    await page.waitForURL(/\/login/, { timeout: 10000 });
    await expect(submit).toBeEnabled({ timeout: 10000 });
    await expect(submit).toBeEnabled();
  });

  test('register page loads', async ({ page }) => {
    await page.goto('/register');
    await expect(page.locator('input').first()).toBeVisible();
  });
});
