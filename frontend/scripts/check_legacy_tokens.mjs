#!/usr/bin/env node
/**
 * Local guard for the design-system consolidation (Phase 5).
 * Scans the frontend source for banned legacy design-token classes and fails
 * if any are found, pointing at the canonical token docs.
 *
 * Mirrors the `token-guard` job in .github/workflows/ci.yml so results are
 * reproducible locally. Banned top-level namespaces that must no longer be
 * used as Tailwind classes (see frontend/design-tokens/README.md):
 *   bg-navy-, text-navy-, border-navy-, bg-bg-, text-text-,
 *   bg-status-, text-status-, border-status-,
 *   bg-chart-literals-, text-chart-literals-,
 *   border-border-primary, border-border-secondary
 *
 * The generator regenerates tailwind.config.ts + globals.css from
 * design-tokens/tokens.json (npm run build:tokens); if you land here because
 * a namespace was re-added to tokens.json, prune it there instead.
 *
 * Usage: node scripts/check_legacy_tokens.mjs [path...]
 */
import { readdirSync, readFileSync, statSync } from "fs";
import { join, relative, extname } from "path";
import { fileURLToPath } from "url";

const FRONTEND = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const DEFAULT_DIRS = [join(FRONTEND, "src")];
const EXTS = new Set([".tsx", ".ts", ".jsx", ".js", ".css"]);

const PATTERNS = [
  "bg-navy-",
  "text-navy-",
  "border-navy-",
  "bg-bg-",
  "text-text-",
  "bg-status-",
  "text-status-",
  "border-status-",
  "bg-chart-literals-",
  "text-chart-literals-",
  "border-border-primary",
  "border-border-secondary",
];

const args = process.argv.slice(2).filter((a) => !a.startsWith("-"));
const dirs = args.length ? args : DEFAULT_DIRS;

function walk(dir, acc) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === "node_modules" || e.name === ".next") continue;
      walk(p, acc);
    } else if (EXTS.has(extname(e.name))) {
      acc.push(p);
    }
  }
  return acc;
}

const files = [];
for (const d of dirs) {
  if (statSync(d).isDirectory()) walk(d, files);
  else files.push(d);
}

const hits = [];
for (const f of files) {
  const content = readFileSync(f, "utf8");
  for (const p of PATTERNS) {
    if (content.includes(p)) hits.push(`${relative(FRONTEND, f)}: ${p}`);
  }
}

if (hits.length) {
  console.error("[check_legacy_tokens] FAIL: banned legacy design-token class(es) found:");
  for (const h of hits) console.error(`  ${h}`);
  console.error("Migrate to the canonical semantic Token layer. See design-tokens/README.md");
  console.error("  npm run build:tokens   (regenerate tailwind + globals from tokens.json)");
  console.error("  node scripts/token-migration/migrate.ts   (codemod)");
  process.exit(1);
}
console.log(`[check_legacy_tokens] PASS: ${files.length} files scanned, no banned legacy design tokens.`);
