import { test, expect } from '@playwright/test';

// These tests verify auth REDIRECTS; they must run without a session.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('Navigation', () => {
  test('landing page loads', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Nazm|nazm/i);
  });

  test('money-audit page requires auth', async ({ page }) => {
    await page.goto('/money-audit');
    const url = page.url();
    const isRedirectedToAuth = url.includes('/login') || url.includes('/register');
    expect(isRedirectedToAuth).toBeTruthy();
  });

  test('dashboard requires auth', async ({ page }) => {
    await page.goto('/dashboard');
    const url = page.url();
    const isRedirectedToAuth = url.includes('/login') || url.includes('/register');
    expect(isRedirectedToAuth).toBeTruthy();
  });

  test('upload page requires auth', async ({ page }) => {
    await page.goto('/upload');
    const url = page.url();
    const isRedirectedToAuth = url.includes('/login') || url.includes('/register');
    expect(isRedirectedToAuth).toBeTruthy();
  });
});
