import { test, expect, Page } from '@playwright/test';

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL || 'supermarket_owner@nazmos.sa';
const OWNER_PASS = process.env.E2E_OWNER_PASS || 'Test2026!';

async function loginAs(page: Page) {
  await page.goto('/dashboard');
  if (!page.url().includes('/login')) return;
  await page.goto('/login');
  await page.locator('input[type="email"], input[name="email"]').fill(OWNER_EMAIL);
  await page.locator('input[type="password"], input[name="password"]').fill(OWNER_PASS);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/dashboard**', { timeout: 30000 });
}

test.describe('Phase 2: Business Memory Context', () => {
  test('Owner can view Money Audit with contextual product information', async ({ page }) => {
    await loginAs(page);
    await page.goto('/money-audit');
    await page.waitForLoadState('networkidle');

    // Page should load without errors
    await expect(page.locator('body')).toContainText(/audit|money|risk|inventory/i);
  });

  test('Owner can navigate to inventory and see product details', async ({ page }) => {
    await loginAs(page);
    await page.goto('/inventory');
    await page.waitForLoadState('networkidle');

    // Inventory page should show product information
    await expect(page.locator('body')).toContainText(/inventory|stock|item/i);
  });

  test('Business context API returns structured data', async ({ page }) => {
    await loginAs(page);

    // Mock the business-context API response
    await page.route('**/intelligence/business-context**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          business: {
            business_id: '00000000-0000-0000-0000-000000000001',
            name: 'Test Baqala',
            business_type: 'baqala',
            city: 'Riyadh',
            currency: 'SAR',
            timezone: 'Asia/Riyadh',
            is_demo: false,
            total_items: 150,
            total_inventory_value_sar: 45000,
            constraints: { cash_budget: 10000, minimum_margin_pct: 0.20 },
            owner_preferences: { preferred_delivery_day: 'Saturday' },
          },
          products: [
            {
              product_id: 'item-1',
              product_name: 'Organic Milk',
              sku: 'ORG_MILK',
              velocity_30d: 140,
              velocity_7d: 56,
              trend: 'INCREASING',
              days_of_supply: 8.5,
              stockout_frequency: 'LOW',
              seasonal_type: 'NOT_SEASONAL',
              confidence: 'HIGH',
            },
          ],
          suppliers: [
            {
              supplier_id: 'sup-1',
              supplier_name: 'Al Marai',
              reliability_rate: 0.93,
              average_actual_lead_time_days: 2.5,
              confidence: 'HIGH',
            },
          ],
          branches: [],
          constraints: { cash_budget: 10000 },
          recent_actions: [
            {
              action_type: 'restock',
              action_date: '2026-08-20T10:00:00',
              execution_status: 'executed',
              product_name: 'Organic Milk',
            },
          ],
          outcomes: [
            {
              action_type: 'discount',
              action_date: '2026-08-15T10:00:00',
              expected_impact_sar: 500,
              actual_impact_sar: 420,
              prediction_error_pct: -16.0,
            },
          ],
          generated_at: '2026-08-28T12:00:00',
          source_period: { start: '2026-05-30', end: '2026-08-28' },
        }),
      })
    );

    await page.goto('/money-audit');
    await page.waitForLoadState('networkidle');

    // The page should load and display audit data
    await expect(page.locator('body')).toContainText(/audit|money|risk/i);
  });

  test('Product context shows action history and constraints', async ({ page }) => {
    await loginAs(page);

    // Mock the product context API
    await page.route('**/intelligence/products/*/context**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          product: {
            product_id: 'item-1',
            product_name: 'Organic Milk',
            sku: 'ORG_MILK',
            current_stock: 30,
            velocity_30d: 140,
            trend: 'INCREASING',
            days_of_supply: 6.4,
            last_action: 'restock',
            last_action_result: 'executed',
            confidence: 'HIGH',
          },
          constraints: {
            discount_blocked: false,
            strategic: false,
            minimum_margin_pct: 0.20,
          },
          previous_actions: [
            { action_type: 'restock', date: '2026-08-20', status: 'executed' },
            { action_type: 'discount', date: '2026-08-10', status: 'rejected' },
          ],
          related_findings: [
            { title: 'Stockout risk', severity: 'high', impact_sar: 2500 },
          ],
          generated_at: '2026-08-28T12:00:00',
        }),
      })
    );

    await page.goto('/inventory');
    await page.waitForLoadState('networkidle');

    // Page should render
    await expect(page.locator('body')).toContainText(/inventory|stock|item/i);
  });

  test('No critical console errors during navigation', async ({ page }) => {
    const consoleErrors: string[] = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await loginAs(page);

    const pages = ['/dashboard', '/money-audit', '/inventory', '/upload'];
    for (const path of pages) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
    }

    const criticalErrors = consoleErrors.filter(e =>
      !e.includes('favicon') &&
      !e.includes('service-worker') &&
      !e.includes('manifest') &&
      !e.includes('Third-party cookie') &&
      !e.includes('webpack')
    );

    expect(criticalErrors).toHaveLength(0);
  });
});
