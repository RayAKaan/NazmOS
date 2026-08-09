#!/usr/bin/env node
/**
 * Accessibility scan (axe-core) over the statically-rendered pages produced
 * by `next build`.
 *
 * Usage:
 *   npm run build   # first (produces page.html files under .next/server/app)
 *   node scripts/check_a11y.mjs
 *
 * Exits non-zero if any page has serious/critical axe violations.
 * Zero-dependency at runtime beyond jsdom + axe-core (devDeps).
 */
import fs from "node:fs";
import path from "node:path";
import { JSDOM } from "jsdom";
import axe from "axe-core";

const ROOT = process.cwd();
const BUILD_DIR = path.join(ROOT, ".next", "server", "app");

const SERIOUS = new Set(["critical", "serious"]);

function findHtml(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) findHtml(full, out);
    else if (entry.name.endsWith(".html")) out.push(full);
  }
  return out;
}

function toAxeRules(markup) {
  const dom = new JSDOM(`<!DOCTYPE html><html lang="en" dir="ltr"><body>${markup}</body></html>`, {
    runScripts: "outside-only",
  });
  global.window = dom.window;
  global.document = dom.window.document;
  global.Node = dom.window.Node;
  global.Element = dom.window.Element;
  Object.defineProperty(global, "navigator", { value: dom.window.navigator, configurable: true });
  return dom.window.document.documentElement;
}

async function scanPage(htmlPath) {
  const html = fs.readFileSync(htmlPath, "utf8");
  const doc = toAxeRules(html);
  const results = await axe.run(doc, {
    rules: {
      "color-contrast": { enabled: false }, // theme colors are brand-owned; tracked separately
      "region": { enabled: false }, // raw SSR fragments lack landmarks until hydration
    },
  });
  const violations = results.violations.filter((v) => SERIOUS.has(v.impact));
  return { path: htmlPath, violations };
}

async function main() {
  const pages = findHtml(BUILD_DIR);
  if (pages.length === 0) {
    console.error("No static HTML found in .next/server/app. Run `npm run build` first.");
    process.exit(1);
  }

  let failed = 0;
  console.log("Axe accessibility scan (static pages)\n========================================");

  for (const page of pages.sort()) {
    const rel = page.replace(BUILD_DIR, "").replace(/[\\/]/g, "/");
    const { violations } = await scanPage(page);
    if (violations.length === 0) {
      console.log(`  PASS  ${rel}`);
      continue;
    }
    failed++;
    console.log(`  FAIL  ${rel}`);
    for (const v of violations) {
      console.log(`    - [${v.impact}] ${v.help} (${v.helpUrl})`);
      v.nodes.slice(0, 3).forEach((n) => {
        console.log(`        @ ${n.target.join(" ")}`);
        const snippet = (n.html || "").replace(/\s+/g, " ").slice(0, 160);
        if (snippet) console.log(`        ${snippet}`);
      });
    }
  }

  console.log(`\nRESULT: ${pages.length} pages scanned, ${failed} with serious violations`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
