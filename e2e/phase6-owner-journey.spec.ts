import { test, expect } from '@playwright/test';

test('Phase 6 owner pilot surface is usable', async ({ page }) => {
  await page.goto('/login');
  await expect(page).toHaveTitle(/NazmOS/i);
  await expect(page.locator('body')).toContainText(/login|sign in/i);
});

test('Phase 6 never exposes OpenCode internals to the owner', async ({ page }) => {
  await page.goto('/');
  const text = await page.locator('body').innerText();
  expect(text).not.toMatch(/OPENAI_API_KEY|GROQ_API_KEY|GOOGLE_AI_API_KEY|docker socket|opencode --/i);
});
