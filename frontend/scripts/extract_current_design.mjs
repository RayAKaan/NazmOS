#!/usr/bin/env node
/**
 * Extract the CURRENT color usage across the frontend into a structured report.
 *
 * This is the "extract-design-system" step applied to the LOCAL codebase (the
 * upstream skill targets public URLs; here we scan source instead). It feeds
 * design-tokens/extraction-report.json so the new token set is genuinely
 * extracted/consolidated from what exists — not invented.
 *
 * Output: design-tokens/extraction-report.json
 *   { generatedAt, files: [...], colors: { "raw-value": [ {file, line, context} ] },
 *     paletteClasses: [...], conflicts: [...] }
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");
const OUT = path.join(ROOT, "design-tokens", "extraction-report.json");

const EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".css", ".mjs"]);
const EXTRA_FILES = ["tailwind.config.ts", "public/manifest.json"];

function walk(dir, acc = []) {
  if (!fs.existsSync(dir)) return acc;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") continue;
      walk(p, acc);
    } else if (EXTENSIONS.has(path.extname(entry.name))) {
      acc.push(p);
    }
  }
  return acc;
}

const files = walk(SRC).filter((f) => !/\.test\./.test(f));
for (const rel of EXTRA_FILES) {
  const p = path.join(ROOT, rel);
  if (fs.existsSync(p)) files.push(p);
}

const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;
const RGB_RE = /rgba?\([^)]*\)/g;
const HSL_RE = /hsla?\([^)]*\)/g;

// tailwind named palette utility classes, e.g. text-red-400, bg-emerald-500/20
const NAMED_CLS_RE =
  /(?:text|bg|border|border-t|border-b|border-l|border-r|ring|from|to|via|outline|fill|stroke|shadow|divide|placeholder)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone|white|black)(?:-[0-9]{2,3})?(?:\/[0-9\[\].]+)?/g;
// tailwind arbitrary-value color classes, e.g. bg-[#14B8A6], text-[oklch(...)]
const ARB_CLS_RE = /(?:text|bg|border|ring|from|to|via|fill|stroke|shadow|outline)-\[([^\]]+)\]/g;

const colors = {}; // raw string -> [{ file, line, context }]
const paletteClasses = new Map(); // className -> count
const arbitraryValues = new Map(); // arbitrary color string -> count
const filesWithColors = [];

function recordColor(map, raw, file, line, context) {
  if (!map[raw]) map[raw] = [];
  map[raw].push({ file, line, context });
}

for (const file of files) {
  const rel = path.relative(ROOT, file).replace(/\\/g, "/");
  const text = fs.readFileSync(file, "utf8");
  const lines = text.split("\n");
  let fileHit = false;

  lines.forEach((lineText, idx) => {
    const line = idx + 1;
    let m;

    HEX_RE.lastIndex = 0;
    while ((m = HEX_RE.exec(lineText)) !== null) {
      recordColor(colors, m[0], rel, line, trim(lineText));
      fileHit = true;
    }
    RGB_RE.lastIndex = 0;
    while ((m = RGB_RE.exec(lineText)) !== null) {
      recordColor(colors, m[0], rel, line, trim(lineText));
      fileHit = true;
    }
    HSL_RE.lastIndex = 0;
    while ((m = HSL_RE.exec(lineText)) !== null) {
      recordColor(colors, m[0], rel, line, trim(lineText));
      fileHit = true;
    }

    NAMED_CLS_RE.lastIndex = 0;
    while ((m = NAMED_CLS_RE.exec(lineText)) !== null) {
      paletteClasses.set(m[0], (paletteClasses.get(m[0]) || 0) + 1);
      fileHit = true;
    }

    ARB_CLS_RE.lastIndex = 0;
    while ((m = ARB_CLS_RE.exec(lineText)) !== null) {
      arbitraryValues.set(m[1], (arbitraryValues.get(m[1]) || 0) + 1);
      fileHit = true;
    }
  });

  if (fileHit) filesWithColors.push(rel);
}

function trim(s) {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length > 160 ? t.slice(0, 157) + "..." : t;
}

const report = {
  generatedAt: new Date().toISOString(),
  scope: "frontend/src + tailwind.config.ts + public/manifest.json",
  filesWithRawColors: filesWithColors.length,
  filesWithRawColorsList: filesWithColors,
  colors: colors,
  paletteClasses: Object.fromEntries([...paletteClasses.entries()].sort((a, b) => b[1] - a[1])),
  arbitraryColorValues: Object.fromEntries([...arbitraryValues.entries()].sort((a, b) => b[1] - a[1])),
};

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(report, null, 2), "utf8");
console.log(`Wrote ${OUT}`);
console.log(`Files with raw colors: ${report.filesWithRawColors}`);
console.log(`Distinct raw color values: ${Object.keys(colors).length}`);
console.log(`Distinct named palette classes: ${Object.keys(report.paletteClasses).length}`);
