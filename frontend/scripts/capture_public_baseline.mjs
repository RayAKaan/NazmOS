#!/usr/bin/env node
// Capture public-route screenshots into e2e/__screenshots__/baseline/
// using the Playwright browser API directly (bypasses the auth setup project,
// so it works without a running backend). No external deps.
import { chromium } from "@playwright/test";
import { mkdirSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(FRONTEND, "e2e", "__screenshots__", "baseline");

const ROUTES = ["/", "/product-demo", "/login", "/register", "/terms", "/privacy"];

const safeFile = (r) => (r === "/" ? "index" : r.replace(/^\/+|\/+$/g, "").replace(/\//g, "__"));

if (process.env.BASE_URL) process.env.BASE = process.env.BASE_URL;
const base = process.env.BASE_URL || "http://localhost:3000";

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
for (const route of ROUTES) {
  await page.goto(base + route, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(900);
  await page.evaluate(() => document.fonts.ready.then(() => {}));
  const file = join(OUT, `${safeFile(route)}.png`);
  await page.screenshot({ path: file, fullPage: true, animations: "disabled" });
  console.log("captured", route, "->", file);
}
await browser.close();
console.log("Public baseline written to", OUT);
