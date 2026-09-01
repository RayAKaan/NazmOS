// Capture redesign screenshots for the report (user verifies; model can't view images).
import { chromium } from "playwright";

const OUT = "docs/landing-page/redesign-shots";
const browser = await chromium.launch();

async function shot(name, route, opts) {
  const page = await browser.newPage(opts || { viewport: { width: 1440, height: 900 } });
  await page.goto(`http://localhost:3000${route}`, { waitUntil: "networkidle" });
  await page.evaluate(() => new Promise((r) => setTimeout(r, 1200)));
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true, animations: "disabled" });
  await page.close();
}

await shot("home-full-final", "/");
await shot("home-dark-final", "/", { viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
await shot("home-mobile-final", "/", { viewport: { width: 390, height: 1200 } });
await shot("home-ar-final", "/", { viewport: { width: 1440, height: 900 } });
await browser.close();
console.log("captured");