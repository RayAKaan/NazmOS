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

interface ActionResult {
  id: string;
  action_type: string;
  priority: number;
  title: string;
  description: string | null;
  status: string;
  classification: string;
  evidence: Record<string, unknown>;
}

function buildAuditPayload(actions: ActionResult[]) {
  return {
    id: 'p1-ui-0001',
    business_id: '00000000-0000-0000-0000-000000000001',
    status: 'completed',
    period_start: null,
    period_end: null,
    money_at_risk_sar: 10000,
    inventory_value_sar: 50000,
    capital_at_risk_sar: 20000,
    revenue_at_risk_sar: 30000,
    gross_profit_at_risk_sar: 8000,
    recoverable_value_low_sar: 1000,
    recoverable_value_high_sar: 3000,
    expected_recovery_sar: 1500,
    recovery_confidence: 'medium',
    dead_stock_value_sar: 200,
    stockout_risk_value_sar: 1500,
    margin_leakage_sar: 300,
    overstock_value_sar: 700,
    money_approved_sar: 0,
    money_recovered_sar: 0,
    confidence_score: 0.82,
    data_quality_score: 0.9,
    missing_data: [],
    created_at: new Date().toISOString(),
    actions,
  };
}

test.describe('Phase 1 decision safety (UI contract)', () => {
  test('Journey 1: confirmed inbound suppresses a tempting reorder', async ({ page }) => {
    await loginAs(page);
    const actions: ActionResult[] = [
      {
        id: 'a-1',
        action_type: 'reorder',
        priority: 3,
        title: 'Restock Organic Cold-Pressed Olive Oil',
        description: 'Projected stock cover is below the 5-day threshold.',
        status: 'suggested',
        classification: 'NORMAL',
        evidence: {
          classification: 'NORMAL',
          confirmed_inbound_qty: 40,
          ghost_po_risk: false,
        },
      },
    ];
    await page.route('**/money-audit/current**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildAuditPayload(actions)),
      })
    );
    await page.goto('/money-audit');
    const section = page.locator('section:has-text("One Thing I Would Not Do")');
    await expect(section).toBeVisible({ timeout: 15000 });
    await expect(section).toContainText(/confirmed inbound unit/i);
    await expect(section).not.toContainText(/ghost-PO/i);
  });

  test('Journey 2: ghost PO risk is surfaced on the do-not-act card', async ({ page }) => {
    await loginAs(page);
    const actions: ActionResult[] = [
      {
        id: 'a-2',
        action_type: 'reorder',
        priority: 3,
        title: 'Restock Organic Cold-Pressed Olive Oil',
        description: 'Projected stock cover is below the 5-day threshold.',
        status: 'suggested',
        classification: 'NORMAL',
        evidence: {
          classification: 'NORMAL',
          confirmed_inbound_qty: 40,
          ghost_po_risk: true,
        },
      },
    ];
    await page.route('**/money-audit/current**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildAuditPayload(actions)),
      })
    );
    await page.goto('/money-audit');
    const section = page.locator('section:has-text("One Thing I Would Not Do")');
    await expect(section).toBeVisible({ timeout: 15000 });
    await expect(section).toContainText(/ghost-PO risk/i);
  });

  test('Journey 3: no confirmed-inbound action keeps the do-not-act card hidden', async ({ page }) => {
    await loginAs(page);
    await page.route('**/money-audit/current**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          buildAuditPayload([
            {
              id: 'a-3',
              action_type: 'reorder',
              priority: 3,
              title: 'Restock Organic Cold-Pressed Olive Oil',
              description: 'Projected stock cover is below the 5-day threshold.',
              status: 'suggested',
              classification: 'NORMAL',
              evidence: { classification: 'NORMAL', confirmed_inbound_qty: 0, ghost_po_risk: false },
            },
          ])
        ),
      })
    );
    await page.goto('/money-audit');
    const section = page.locator('section:has-text("One Thing I Would Not Do")');
    await expect(section).not.toBeVisible({ timeout: 15000 });
  });
});
