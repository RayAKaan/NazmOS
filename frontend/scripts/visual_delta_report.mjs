#!/usr/bin/env node
/**
 * Visual regression delta report (depend-free).
 *
 * The pixel diff itself is produced by Playwright's toHaveScreenshot
 * (frontend/e2e/visual-baseline.spec.ts) — it writes expected/actual/diff PNGs
 * under test-results/ whenever a route diverges from the stored baseline.
 * This script aggregates those artifacts and a Playwright JSON report into a
 * human- and machine-readable report, and seeds the manual classification
 * step the design-system mission requires:
 *
 *   EXPECTED CONSOLIDATION   -> previously distinct colors now share one token
 *   UNINTENDED REGRESSION    -> layout/spacing/type regression (FIX before going on)
 *
 * Usage:
 *   node scripts/visual_delta_report.mjs [--json report.json] [--out DESIGN_SYSTEM_VISUAL_REPORT.md]
 *   (defaults: scans test-results/ for diffs; writes DESIGN_SYSTEM_VISUAL_REPORT.md)
 */
import { readFileSync, readdirSync, existsSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const TEST_RESULTS = join(ROOT, "test-results");
const BASELINE_DIR = join(ROOT, "e2e", "__screenshots__", "baseline");

const args = process.argv.slice(2);
const argOf = (flag) => {
  const i = args.indexOf(flag);
  return i >= 0 && args[i + 1] ? args[i + 1] : undefined;
};
const jsonReport = argOf("--json");
const outFile = argOf("--out") ?? "DESIGN_SYSTEM_VISUAL_REPORT.md";

function routesWithDiffImages() {
  if (!existsSync(TEST_RESULTS)) return [];
  const found = new Set();
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith("-diff.png") || e.name.endsWith("-actual.png")) {
        const rt = e.name
          .replace(/-diff\.png$/, "")
          .replace(/-actual\.png$/, "")
          .replace(/__/g, "/");
        if (rt) found.add(rt === "index" ? "/" : `/${rt}`);
      }
    }
  };
  walk(TEST_RESULTS);
  return [...found];
}

function parseJsonReport(path) {
  if (!path || !existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return null;
  }
}

function collectFailures(json) {
  const failures = new Set();
  if (!json?.suites) return failures;
  const visit = (suites) => {
    for (const s of suites || []) {
      for (const t of s.specs || []) {
        for (const ok of t.tests || []) {
          for (const res of ok.results || []) {
            if (res.status === "failed") {
              // test title is "baseline /route" -> extract route
              const title = t.title || "";
              const m = title.match(/baseline\s+(\S+)/);
              if (m) failures.add(m[1]);
            }
          }
        }
      }
      visit(s.suites);
    }
  };
  visit(json.suites);
  return failures;
}

function baselineRoutes() {
  if (!existsSync(BASELINE_DIR)) return [];
  return readdirSync(BASELINE_DIR)
    .filter((f) => f.endsWith(".png"))
    .map((f) => (f === "index.png" ? "/" : `/${f.replace(/\.png$/, "").replace(/__/g, "/")}`));
}

const json = parseJsonReport(jsonReport);
const diffRoutes = routesWithDiffImages();
const jsonFailures = json ? collectFailures(json) : new Set();
const affected = [...new Set([...diffRoutes, ...jsonFailures])].sort();

const captured = baselineRoutes().length;

const link = (route) => `[${route}](http://localhost:3000${route})`;

const lines = [];
lines.push("# DESIGN_SYSTEM_VISUAL_REPORT", "");
lines.push("## Summary");
lines.push("");
lines.push(`- **Baseline screenshots:** ${captured} routes under \`e2e/__screenshots__/baseline/\``);
lines.push(`- **Source:** Playwright \`toHaveScreenshot\` (no external visual-regression service)`);
lines.push(`- **Delta artifacts:** \`test-results/**/*-{expected,actual,diff}.png\``);
lines.push(`- **Affected routes detected:** ${affected.length}`);
lines.push("");
lines.push("## Baseline routes captured");
lines.push("");
for (const r of baselineRoutes()) lines.push(`- ${link(r)}`);
lines.push("");
lines.push("## Deltas — manual classification required");
lines.push("");
lines.push("Every delta must be classified as `EXPECTED CONSOLIDATION` or `UNINTENDED REGRESSION`.");
lines.push("Do not auto-approve all differences.");
lines.push("");
lines.push("| Route | Detection | Playwright failure | Classification | Notes |");
lines.push("|---|---|---|---|---|");
const detection = (r) => (diffRoutes.includes(r) ? "diff PNG" : jsonFailures.has(r) ? "JSON" : "unknown");
for (const r of affected.length ? affected : baselineRoutes()) {
  lines.push(`| ${link(r)} | ${detection(r)} | ${jsonFailures.has(r) ? "FAIL" : "pass"} | | |`);
}
lines.push("");
lines.push("## Guide");
lines.push("");
lines.push("- **EXPECTED CONSOLIDATION**: previously distinct legacy colors (e.g. `navy-*`, `status-*`, `bg-*`, `text-*`) now map to one canonical Tier-2 token, so several routes shift to the shared color. Accept only if spacing/layout/type are unchanged.");
lines.push("- **UNINTENDED REGRESSION**: any layout, spacing, component-hierarchy, or typography change must be fixed before continuing.");
lines.push("");
writeFileSync(join(ROOT, "_report", outFile), lines.join("\n"), "utf8");
console.log(`[visual_delta_report] wrote ${outFile} (${affected.length} affected routes, ${captured} baselined)`);
