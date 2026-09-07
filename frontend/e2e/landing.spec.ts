import { test, expect, Page } from "@playwright/test";

// Public landing page (Business Universe) — no backend required, no session.
test.use({ storageState: { cookies: [], origins: [] } });

async function gotoHome(page: Page) {
  await page.goto("/");
  await page.getByRole("heading", { level: 1 }).first().waitFor();
}

test.describe("Business Universe (public home)", () => {
  test("renders the thesis and primary navigation", async ({ page }) => {
    await gotoHome(page);
    await expect(
      page.getByText("Business is a system.", { exact: false }).first(),
    ).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Universe" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "NazmOS" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Audit" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Company" })).toBeVisible();
  });

  test("shows the flagship dark world to a brand-new visitor and does not leak it", async ({ page }) => {
    await gotoHome(page);
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(page.locator("canvas[data-shader-theme=\"dark\"]")).toBeVisible();
    // Leaving the universe releases the flagship default so the site's own
    // theme system (system-aware) applies on other pages.
    await page.goto("/terms");
    await expect(page.locator("html")).not.toHaveClass(/dark/);
  });

  test("the theme switch flips the shader between dark and light worlds", async ({ page }) => {
    await gotoHome(page);
    await expect(page.locator("html")).toHaveClass(/dark/);
    await page.getByRole("button", { name: "Switch to light theme" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await expect(page.locator("canvas[data-shader-theme=\"light\"]")).toBeVisible();
    // The preference persists and the switch now reads as "switch back".
    await page.goto("/terms");
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.goto("/");
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await page.getByRole("button", { name: "Switch to dark theme" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expect(page.locator("canvas[data-shader-theme=\"dark\"]")).toBeVisible();
  });

  test("exposes the five signals as accessible buttons", async ({ page }) => {
    await gotoHome(page);
    for (const label of ["Sales", "Inventory", "Demand", "Suppliers", "Cost"]) {
      await expect(page.getByRole("button", { name: label, exact: true }).first()).toBeVisible();
    }
  });

  test("explore NazmOS convergence opens and links onward to the product page", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "NazmOS" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "The operating intelligence layer." })).toBeVisible();
    await expect(page.getByRole("link", { name: "Explore full NazmOS" })).toBeVisible();
    // Product page still resolves.
    await page.getByRole("link", { name: "Explore full NazmOS" }).click();
    await expect(page).toHaveURL(/\/products\/nazmos/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("ESC returns from the NazmOS view to the universe", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "NazmOS" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "The operating intelligence layer." })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("the Company state explains the builder and ESC returns to the universe", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Company" }).click();
    await expect(page.getByText("Intelligence for real business.", { exact: false }).first()).toBeVisible();
    // The company links onward to its first product.
    await expect(page.getByRole("button", { name: "Meet NazmOS" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  });

  test("focusing a signal opens its domain panel", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("button", { name: "Sales", exact: true }).first().click();
    await expect(page.getByRole("heading", { level: 2, name: "Revenue is a signal." })).toBeVisible();
    await expect(page.getByRole("button", { name: "See how NazmOS reads this" })).toBeVisible();
    // A focused domain can only progress inward — the audit launch lives in NazmOS.
    await expect(page.getByRole("button", { name: "Request a Business Audit" })).toHaveCount(0);
  });

  test("the Audit state embeds the real guest audit uploader", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Audit" }).click();
    // Not a placeholder: the production uploader is present.
    await expect(page.getByText("Upload your sales file", { exact: false }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Analyze Free" })).toBeVisible();
    // The analysis button starts disabled until a file is chosen.
    await expect(page.getByRole("button", { name: "Analyze Free" })).toBeDisabled();
  });

  test("language switch flips the document to RTL/Arabic", async ({ page }) => {
    await gotoHome(page);
    await page.getByRole("button", { name: "عربي" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
    await expect(page.getByText("العمل نظام.", { exact: false }).first()).toBeVisible();
  });

  test("mobile menu opens and reaches the audit", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await gotoHome(page);
    await page.getByRole("button", { name: "Open menu" }).click();
    const mobile = page.getByRole("navigation", { name: "Mobile" });
    await expect(mobile).toBeVisible();
    await mobile.getByRole("button", { name: "Audit" }).click();
    await expect(page.getByRole("button", { name: "Analyze Free" })).toBeVisible();
  });

  test("keyboard focus is reachable on the primary nav", async ({ page }) => {
    await gotoHome(page);
    const audit = page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Audit" });
    await audit.focus();
    await expect(audit).toBeFocused();
  });

  test("respects prefers-reduced-motion (thesis still renders)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await gotoHome(page);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  });

  test("reduced-motion fallback also adapts to the light world", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await gotoHome(page);
    // No shader canvas under reduced motion — the static SVG fallback renders.
    await expect(page.locator("canvas[data-shader-theme]")).toHaveCount(0);
    await page.getByRole("button", { name: "Switch to light theme" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  });
});