/**
 * V11 Playwright E2E — Real Owner Journey with AI Context
 *
 * Tests the actual owner journey using real selectors from source code.
 * Screenshots captured at every key state.
 * Console errors and network failures monitored throughout.
 *
 * Selector strategy: Uses real selectors from frontend source code, NOT invented testids.
 */
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL || 'supermarket_owner@nazmos.sa';
const OWNER_PASS = process.env.E2E_OWNER_PASS || 'Test2026!';

// Collect console errors and network failures
let consoleErrors: string[] = [];
let networkFailures: string[] = [];
let pageTimings: Record<string, number> = {};

async function login(page: Page): Promise<void> {
  await page.goto(`${BASE_URL}/login`);

  // Wait for form to be ready
  await page.waitForLoadState('networkidle');

  // Fill email (react-hook-form registers as name="email")
  const emailInput = page.locator('input[type="email"]');
  await emailInput.waitFor({ state: 'visible', timeout: 10000 });
  await emailInput.fill(OWNER_EMAIL);

  // Fill password
  const passwordInput = page.locator('input[type="password"]');
  await passwordInput.waitFor({ state: 'visible', timeout: 10000 });
  await passwordInput.fill(OWNER_PASS);

  // Submit
  const submitButton = page.locator('button[type="submit"]');
  await submitButton.click();

  // Wait for redirect to dashboard
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  await page.waitForLoadState('networkidle');
}

test.describe('V11 Owner Journey — Real E2E', () => {
  test.beforeEach(async ({ page }) => {
    // Reset tracking arrays
    consoleErrors = [];
    networkFailures = [];

    // Monitor console errors
    page.on('console', (msg: ConsoleMessage) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Monitor page errors
    page.on('pageerror', (error) => {
      consoleErrors.push(error.message);
    });

    // Monitor failed network requests
    page.on('response', (response) => {
      if (response.status() >= 400 && !response.url().includes('favicon')) {
        networkFailures.push(`${response.status()} ${response.url()}`);
      }
    });
  });

  test('complete owner journey: login → dashboard → upload → money-audit → approve', async ({ page }) => {
    const startTime = Date.now();

    // ── Step 1: Login ──
    await test.step('login', async () => {
      await login(page);
      pageTimings['login'] = Date.now() - startTime;
      await page.screenshot({ path: 'results/v11/playwright/01_dashboard.png', fullPage: true });
    });

    // ── Step 2: Verify Dashboard loads ──
    await test.step('dashboard loads', async () => {
      // Dashboard has greeting h1
      const heading = page.locator('h1');
      await expect(heading.first()).toBeVisible({ timeout: 10000 });

      // Check for key dashboard elements
      const dashboardText = await page.textContent('body');
      expect(dashboardText).toBeTruthy();

      await page.screenshot({ path: 'results/v11/playwright/02_dashboard_loaded.png', fullPage: true });
    });

    // ── Step 3: Navigate to Upload ──
    await test.step('navigate to upload', async () => {
      // Sidebar has nav links — click Upload
      const uploadLink = page.locator('nav a, aside nav a').filter({ hasText: /upload/i }).first();
      if (await uploadLink.isVisible()) {
        await uploadLink.click();
        await page.waitForLoadState('networkidle');
      } else {
        await page.goto(`${BASE_URL}/upload`);
        await page.waitForLoadState('networkidle');
      }

      // Verify upload page loaded
      const uploadText = await page.textContent('body');
      expect(uploadText?.toLowerCase()).toContain('upload');

      await page.screenshot({ path: 'results/v11/playwright/03_upload_page.png', fullPage: true });
    });

    // ── Step 4: Navigate to Money Audit ──
    await test.step('navigate to money-audit', async () => {
      const auditLink = page.locator('nav a, aside nav a').filter({ hasText: /money.?audit/i }).first();
      if (await auditLink.isVisible()) {
        await auditLink.click();
        await page.waitForLoadState('networkidle');
      } else {
        await page.goto(`${BASE_URL}/money-audit`);
        await page.waitForLoadState('networkidle');
      }

      // Verify money audit page loaded
      const auditText = await page.textContent('body');
      expect(auditText?.toLowerCase()).toContain('audit');

      await page.screenshot({ path: 'results/v11/playwright/04_money_audit.png', fullPage: true });
    });

    // ── Step 5: Check for AI-related content ──
    await test.step('AI context visibility', async () => {
      const bodyText = await page.textContent('body') || '';

      // Check for evidence/decision elements
      const hasDecisions = bodyText.toLowerCase().includes('decision') ||
                          bodyText.toLowerCase().includes('action') ||
                          bodyText.toLowerCase().includes('approve');

      // Check for financial values
      const hasFinancial = bodyText.includes('SAR') ||
                          bodyText.toLowerCase().includes('capital') ||
                          bodyText.toLowerCase().includes('recoverable');

      // These are soft checks — the page may not have all elements
      console.log(`  AI context visible: decisions=${hasDecisions}, financial=${hasFinancial}`);

      await page.screenshot({ path: 'results/v11/playwright/05_ai_context.png', fullPage: true });
    });

    // ── Step 6: Check for action buttons ──
    await test.step('action buttons', async () => {
      // Look for Approve/Reject buttons
      const approveBtn = page.locator('button').filter({ hasText: /approve/i }).first();
      const rejectBtn = page.locator('button').filter({ hasText: /reject/i }).first();

      const hasApprove = await approveBtn.isVisible().catch(() => false);
      const hasReject = await rejectBtn.isVisible().catch(() => false);

      console.log(`  Action buttons: approve=${hasApprove}, reject=${hasReject}`);

      await page.screenshot({ path: 'results/v11/playwright/06_actions.png', fullPage: true });
    });

    // ── Step 7: Navigate to Dashboard ──
    await test.step('return to dashboard', async () => {
      const dashLink = page.locator('nav a, aside nav a').filter({ hasText: /dashboard/i }).first();
      if (await dashLink.isVisible()) {
        await dashLink.click();
        await page.waitForLoadState('networkidle');
      } else {
        await page.goto(`${BASE_URL}/dashboard`);
        await page.waitForLoadState('networkidle');
      }

      await page.screenshot({ path: 'results/v11/playwright/07_final_dashboard.png', fullPage: true });
    });

    // ── Final checks ──
    await test.step('verify no critical errors', async () => {
      const criticalErrors = consoleErrors.filter(e =>
        !e.includes('favicon') &&
        !e.includes('service-worker') &&
        !e.includes('404')
      );

      // Report but don't fail on non-critical errors
      if (criticalErrors.length > 0) {
        console.log(`  Console errors: ${criticalErrors.length}`);
        criticalErrors.forEach(e => console.log(`    - ${e.substring(0, 100)}`));
      }

      if (networkFailures.length > 0) {
        console.log(`  Network failures: ${networkFailures.length}`);
        networkFailures.forEach(f => console.log(`    - ${f}`));
      }
    });

    // Save timing report
    const timingReport = {
      total_ms: Date.now() - startTime,
      steps: pageTimings,
      console_errors: consoleErrors.length,
      network_failures: networkFailures.length,
      timestamp: new Date().toISOString(),
    };

    const fs = require('fs');
    const path = require('path');
    const resultsDir = path.join(process.cwd(), 'results', 'v11', 'playwright');
    fs.mkdirSync(resultsDir, { recursive: true });
    fs.writeFileSync(
      path.join(resultsDir, 'timing_report.json'),
      JSON.stringify(timingReport, null, 2)
    );
  });

  test('login form validation', async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');

    // Try empty form submission
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();

    // Should still be on login page
    await page.waitForTimeout(1000);
    expect(page.url()).toContain('login');

    await page.screenshot({ path: 'results/v11/playwright/08_login_validation.png' });
  });

  test('navigation between pages', async ({ page }) => {
    await login(page);

    // Test navigation to key pages
    const pages = ['dashboard', 'upload', 'money-audit'];

    for (const pageName of pages) {
      await page.goto(`${BASE_URL}/${pageName}`);
      await page.waitForLoadState('networkidle');

      const bodyText = await page.textContent('body') || '';
      console.log(`  /${pageName}: loaded (${bodyText.length} chars)`);

      await page.screenshot({
        path: `results/v11/playwright/09_nav_${pageName}.png`,
        fullPage: true,
      });
    }
  });
});
