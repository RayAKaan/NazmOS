// Overflow probe for the redesigned landing (EN + AR) at narrow widths.
// Run: node scripts/overflow_probe.mjs   (requires `next start` on :3000)
import { chromium } from "playwright";

const SIZES = [320, 375, 640, 768];
const LANGS = ["en", "ar"];

const browser = await chromium.launch();
let failed = 0;

for (const lang of LANGS) {
  for (const width of SIZES) {
    const page = await browser.newPage({
      viewport: { width: lang === "ar" ? 1280 : width, height: 800 },
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));

    await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
    if (lang === "ar") {
      await page.getByRole("button", { name: "عربي" }).click();
      await page.locator("html").waitFor({ state: "attached" });
      await page.setViewportSize({ width, height: 800 });
    }
    await page.waitForTimeout(400);

    const result = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      iw: document.documentElement.clientWidth,
      bodySw: document.body.scrollWidth,
    }));

    const overflow = Math.max(result.sw, result.bodySw) - result.iw;
    const ok = overflow <= 0 && errors.length === 0;
    if (!ok) failed++;
    console.log(
      `${lang} ${width}px  overflow=${overflow}px  ${ok ? "PASS" : "FAIL"}` +
        (errors.length ? `  pageErrors=${errors.join(" | ")}` : ""),
    );
    await page.close();
  }
}

await browser.close();
console.log(failed === 0 ? "OVERFLOW PROBE: PASS" : `OVERFLOW PROBE: FAIL (${failed})`);
process.exit(failed === 0 ? 0 : 1);