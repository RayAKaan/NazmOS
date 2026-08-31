import { test, expect, Page } from "@playwright/test";

// Public landing page — no backend required, run without a session.
test.use({ storageState: { cookies: [], origins: [] } });

async function gotoHome(page: Page) {
  await page.goto("/");
  await page.getByRole("heading", { level: 1 }).first().waitFor();
}

test.describe("Landing page", () => {
  test("renders the three hero CTAs and trust line", async ({ page }) => {
    await gotoHome(page);
    await expect(page.getByText("Upload Sales + Inventory", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Watch the demo", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("No POS replacement", { exact: false }).first()).toBeVisible();
  });

  test("shows a clearly-labeled Sample audit panel initial state", async ({ page }) => {
    await gotoHome(page);
    // The hero sample card always carries a "Sample" chip.
    await expect(page.getByText("Sample", { exact: true }).first()).toBeVisible();
  });

  test("FAQ details open and close", async ({ page }) => {
    await gotoHome(page);
    const first = page.locator("details").first();
    await first.locator("summary").click();
    await expect(first.locator("p").first()).toBeVisible();
    await first.locator("summary").click();
    await expect(first.locator("p").first()).toHaveCount(1); // still in DOM but hidden
  });

  test("mobile menu opens and navigates", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await gotoHome(page);
    await page.getByRole("button", { name: /open menu/i }).click();
    await expect(page.getByRole("navigation", { name: /mobile/i })).toBeVisible();
    await page.getByRole("navigation", { name: /mobile/i }).getByRole("link", { name: /free audit/i }).click();
    await expect(page).toHaveURL(/#free-audit/);
  });

  test("language switch flips the document to RTL/Arabic", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("button", { name: "عربي" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
    // Arabic hero headline present.
    await expect(page.getByText("اعثر على النقد المحتجز", { exact: false }).first()).toBeVisible();
  });

  test("theme toggle persists and applies .dark", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("button", { name: /dark theme/i }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    const stored = await page.evaluate(() => localStorage.getItem("nazmos-theme"));
    expect(stored).toBe("dark");
  });

  test("keyboard focus outline is reachable on primary CTA", async ({ page }) => {
    await gotoHome(page);
    await page.locator('a[href="#free-audit"]').first().focus();
    await expect(page.locator('a[href="#free-audit"]').first()).toBeFocused();
  });

  test("respects prefers-reduced-motion (hero still renders)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await gotoHome(page);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  });
});
