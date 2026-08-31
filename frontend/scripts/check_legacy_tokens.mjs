#!/usr/bin/env node
/**
 * Local guard for the design-system consolidation.
 * Scans the frontend source for banned legacy / forbidden design-token classes
 * and fails if any are found, pointing at the canonical token docs.
 *
 * Mirrors the `token-guard` job in .github/workflows/ci.yml so results are
 * reproducible locally.
 *
 * The generator regenerates tailwind.config.ts + globals.css from
 * design-tokens/tokens.json (npm run build:tokens); if you land here because a
 * namespace was re-added to tokens.json, prune it there instead.
 *
 * Usage:
 *   node scripts/check_legacy_tokens.mjs [path...]   # scan default (frontend/src)
 *   node scripts/check_legacy_tokens.mjs --self-test # assert positive/negative cases
 */
import { readdirSync, readFileSync, statSync } from "fs";
import { join, relative, extname } from "path";
import { fileURLToPath } from "url";

const FRONTEND = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const DEFAULT_DIRS = [join(FRONTEND, "src")];
const EXTS = new Set([".tsx", ".ts", ".jsx", ".js", ".css"]);

// Forbidden legacy / legacy-derived border tokens. Each is matched as a whole
// Tailwind class token (word boundary), so legitimate canonical tokens such as
// border-border, bg-background, text-foreground, bg-primary, text-primary,
// bg-secondary and text-secondary are never falsely flagged.
const FORBIDDEN = [
  { name: "border-primary", re: /\bborder-primary\b/ },
  { name: "border-secondary", re: /\bborder-secondary\b/ },
  { name: "border-border-primary", re: /\bborder-border-primary\b/ },
  { name: "border-border-secondary", re: /\bborder-border-secondary\b/ },
  { name: "bg-bg-*", re: /\bbg-bg-/ },
  { name: "text-text-*", re: /\btext-text-/ },
  { name: "bg-navy-*", re: /\bbg-navy-/ },
  { name: "text-navy-*", re: /\btext-navy-/ },
  { name: "border-navy-*", re: /\bborder-navy-/ },
  { name: "bg-status-*", re: /\bbg-status-/ },
  { name: "text-status-*", re: /\btext-status-/ },
];

function detect(content) {
  const hits = [];
  for (const p of FORBIDDEN) {
    if (p.re.test(content)) hits.push(p.name);
  }
  return hits;
}

// ----- self test (positive + negative cases) -----
function selfTest() {
  // Every string here must be DETECTED (i.e. must fail the guard).
  const positives = [
    "border-primary",
    "focus:border-primary",
    "hover:border-primary/30",
    "border-primary/40",
    "border-secondary",
    "border-secondary/60",
    "border-border-primary",
    "border-border-secondary",
    "bg-bg-primary",
    "bg-bg-surface",
    "text-text-primary",
    "text-text-subtle",
    "bg-navy-deep",
    "text-navy-text",
    "border-navy-panel-2",
    "bg-status-error",
    "text-status-info",
  ];
  // Every string here must NOT be detected (i.e. must pass the guard).
  const negatives = [
    "border-border",
    "border-border/30",
    "border",
    "bg-background",
    "text-foreground",
    "bg-primary",
    "text-primary",
    "bg-primary/10",
    "bg-secondary",
    "text-secondary",
    "bg-secondary/10",
    "text-muted-foreground",
    "bg-card",
    "bg-popover",
    "border-border bg-primary text-foreground",
  ];

  let failed = 0;
  for (const s of positives) {
    if (detect(s).length === 0) {
      console.error(`[self-test] FAIL: expected to DETECT but did not: "${s}"`);
      failed++;
    }
  }
  for (const s of negatives) {
    const hits = detect(s);
    if (hits.length > 0) {
      console.error(`[self-test] FAIL: expected ALLOW but detected (${hits.join(", ")}): "${s}"`);
      failed++;
    }
  }
  if (failed) {
    console.error(`[self-test] ${positives.length + negatives.length} cases, ${failed} failed.`);
    process.exit(1);
  }
  console.log(
    `[self-test] PASS: ${positives.length} positive + ${negatives.length} negative cases all correct.`
  );
}

// ----- scan mode -----
const args = process.argv.slice(2).filter(Boolean);
if (args.includes("--self-test")) {
  selfTest();
  process.exit(0);
}

const dirs = args.filter((a) => !a.startsWith("-")).length
  ? args.filter((a) => !a.startsWith("-"))
  : DEFAULT_DIRS;

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
  const found = detect(content);
  for (const name of found) hits.push(`${relative(FRONTEND, f)}: ${name}`);
}

if (hits.length) {
  console.error("[check_legacy_tokens] FAIL: forbidden design-token class(es) found:");
  for (const h of hits) console.error(`  ${h}`);
  console.error("Migrate to the canonical semantic Token layer. See design-tokens/README.md");
  console.error("  npm run build:tokens   (regenerate tailwind + globals from tokens.json)");
  console.error("  node scripts/token-migration/migrate.ts   (codemod)");
  process.exit(1);
}
console.log(`[check_legacy_tokens] PASS: ${files.length} files scanned, no forbidden design tokens.`);
