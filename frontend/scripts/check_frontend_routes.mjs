#!/usr/bin/env node
/**
 * check_frontend_routes.mjs
 *
 * Zero-dependency route/link integrity checker for the NazmOS Next.js app-router.
 * CI regression protection: a broken internal nav link must never ship again.
 *
 * How it works:
 *   1. Statically builds the real route list from every src/app page.tsx file,
 *      respecting Next.js route groups ((dashboard), (auth)) and dynamic
 *      segments ([id]).
 *   2. Scans the whole src/ tree for internal navigation: <Link href=...>,
 *      router.push/replace/prefetch(...), redirect(...) and
 *      window.location.href = "...".
 *   3. Diffs every href against the route list:
 *        - href -> no matching page .................. FAIL (exit 1)
 *        - page with no inbound reference ........... ORPHANED (must be
 *          justified in JUSTIFIED_ORPHANS or it is a FAIL)
 *   4. Also parses next.config.js redirects + rewrites and sitemap.ts so that
 *      legitimately reachable aliases are not reported as broken.
 *
 * Exit codes: 0 = clean, 1 = at least one unjustified FAIL, 2 = internal error.
 */

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, relative, sep, resolve, dirname } from "node:path";

const FRONTEND_ROOT = resolve(import.meta.dirname, "..");
const SRC_DIR = join(FRONTEND_ROOT, "src");
const APP_DIR = join(SRC_DIR, "app");

// ---------------------------------------------------------------------------
// 1. Build the real route list from the filesystem.
// ---------------------------------------------------------------------------

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...walk(full));
    } else if (entry === "page.tsx") {
      out.push(full);
    }
  }
  return out;
}

/**
 * Converts an absolute page.tsx path into its URL path, stripping route groups.
 * e.g. .../(dashboard)/inventory/page.tsx -> "/inventory"
 */
function pagePathToRoute(pageFile) {
  const relPath = relative(APP_DIR, pageFile); // "inventory/page.tsx"
  const parts = relPath.split(sep).filter(Boolean);
  parts.pop(); // remove "page.tsx"
  const cleaned = parts.filter((p) => !(p.startsWith("(") && p.endsWith(")")));
  return "/" + cleaned.join("/");
}

const pageFiles = walk(APP_DIR).sort();
const routes = new Set(pageFiles.map(pagePathToRoute).map((r) => r || "/"));

// ---------------------------------------------------------------------------
// 2. Parse next.config.js for redirects + rewrites (reachable aliases).
// ---------------------------------------------------------------------------

function parseNextConfig() {
  const cfgPath = join(FRONTEND_ROOT, "next.config.js");
  if (!existsSync(cfgPath)) return { redirects: [], rewrites: [] };
  const src = readFileSync(cfgPath, "utf8");
  const stripComments = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

  const redirects = [];
  const rewrites = [];
  for (const m of stripComments.matchAll(/source:\s*["'`]([^"'`]+)["'`][\s\S]*?destination:\s*["'`]([^"'`]+)["'`]/g)) {
    redirects.push({ source: m[1], destination: m[2] });
  }
  for (const m of stripComments.matchAll(/source:\s*["'`]([^"'`]+)["'`][\s\S]*?destination:\s*["'`]([^"'`]+)["'`]/g)) {
    if (!redirects.some((r) => r.source === m[1])) rewrites.push({ source: m[1], destination: m[2] });
  }
  return { redirects, rewrites };
}

const { redirects, rewrites } = parseNextConfig();
const knownAliases = new Set([...redirects, ...rewrites].map((r) => r.source));

// ---------------------------------------------------------------------------
// 3. Scan all source files for internal navigation calls.
// ---------------------------------------------------------------------------

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);

function walkSources(dir, acc = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (entry === "node_modules" || entry === ".next") continue;
    if (statSync(full).isDirectory()) {
      walkSources(full, acc);
    } else if (SOURCE_EXTENSIONS.has(entry.slice(entry.lastIndexOf(".")))) {
      acc.push(full);
    }
  }
  return acc;
}

/**
 * Extracts literal string/navigation targets from a JS/TS source file.
 * Returns [{ raw, target, file, line }].
 */
function scanFileForTargets(file) {
  const src = readFileSync(file, "utf8");
  const targets = [];

  // Track line numbers by matching against the original text.
  const addTarget = (startIdx, raw) => {
    if (raw == null) return;
    const trimmed = raw.trim();
    if (!trimmed) return;
    const line = src.slice(0, startIdx).split("\n").length;
    targets.push({ file: relative(SRC_DIR, file), line, raw: trimmed });
  };

  // Match helper: run a regex with capture over the whole file text.
  const collect = (re, captureIdx) => {
    let m;
    while ((m = re.exec(src)) !== null) {
      addTarget(m.index, m[captureIdx]);
      if (m.index === re.lastIndex) re.lastIndex++;
    }
  };

  // <Link href="..."> / <Link href='...'> / <Link href={`...`}> (may span lines)
  collect(/<Link\b[^>]*?\shref=(["'`])([^"'`]+)\1/g, 2);

  // <Link href={ '...' }> / <Link href={`...`}>
  collect(/<Link\b[^>]*?\shref=\{\s*(["'`])([^"'`]+)\1\s*\}/g, 2);

  // Object-literal href: "/..." in nav/config arrays (e.g. Sidebar baseNavItems).
  collect(/\bhref:\s*(["'`])(\/[^"'`]+)\1/g, 2);

  // router.push / replace / prefetch("...") from next/navigation
  collect(/\brouter\.(push|replace|prefetch)\(\s*(["'`])([^"'`]+)\2\s*\)/g, 3);

  // redirect("...") / permanentRedirect("...") from next/navigation
  collect(/\b(?:permanentRedirect|redirect)\(\s*(["'`])([^"'`]+)\1\s*\)/g, 2);

  // window.location.href = "..."
  collect(/window\.location\.href\s*=\s*(["'`])([^"'`]+)\1/g, 2);

  return targets;
}

const sourceFiles = walkSources(SRC_DIR);
const allTargets = [];
for (const file of sourceFiles) {
  allTargets.push(...scanFileForTargets(file));
}

// ---------------------------------------------------------------------------
// 4a. Reachability: which source files are actually used by the app?
//     Links found in dead (unimported) components are reported as WARNINGS
//     rather than FAILs — dead code can never ship a broken link.
// ---------------------------------------------------------------------------

const APP_ENTRY = APP_DIR; // everything under src/app is reachable (routes/layouts)

function resolveLocalImport(fromFile, specifier) {
  if (specifier.startsWith("@/")) {
    return join(SRC_DIR, specifier.slice(2));
  }
  if (!specifier.startsWith(".")) return null; // bare package
  return resolve(dirname(fromFile), specifier);
}

function importExists(candidate) {
  if (existsSync(candidate)) {
    if (statSync(candidate).isDirectory()) return null;
    return candidate;
  }
  for (const ext of [".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs"]) {
    if (existsSync(candidate + ext)) return candidate + ext;
  }
  if (existsSync(join(candidate, "index.tsx"))) return join(candidate, "index.tsx");
  if (existsSync(join(candidate, "index.ts"))) return join(candidate, "index.ts");
  return null;
}

function reachableFiles() {
  const seen = new Set();
  const queue = [];
  for (const f of sourceFiles) {
    if (f.startsWith(APP_ENTRY + sep)) {
      seen.add(f);
      queue.push(f);
    }
  }
  const importRe = /(?:from\s*["']|import\s*\(\s*["']|import\s+["']|require\(\s*["'])([^"']+)(?:["'])/g;
  while (queue.length) {
    const file = queue.pop();
    let src;
    try {
      src = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    let m;
    importRe.lastIndex = 0;
    while ((m = importRe.exec(src)) !== null) {
      const resolved = resolveLocalImport(file, m[1]);
      if (!resolved) continue;
      const target = importExists(resolved);
      if (target && !seen.has(target)) {
        seen.add(target);
        queue.push(target);
      }
    }
  }
  return seen;
}

const reachable = reachableFiles();

// ---------------------------------------------------------------------------
// 4. Resolve raw targets into route hrefs (strip query/hash, anchors, externals).
// ---------------------------------------------------------------------------

function normalizeHref(raw) {
  let href = raw.trim();
  if (!href || href.startsWith("#")) return null; // in-page anchor
  if (/^(https?:|mailto:|tel:|wa\.me|www\.|data:|\/\/)/i.test(href)) return null; // external
  href = href.split(/[?#]/)[0]; // strip query string + hash
  if (!href.startsWith("/")) return null; // relative path we cannot resolve statically
  href = href.replace(/\/+$/, "") || "/"; // trailing slash
  return href;
}

function routeMatches(href) {
  if (routes.has(href)) return true;
  // dynamic segment: /chain/abc should match page /chain (no), but /x/[id] pattern:
  const hrefParts = href.split("/").filter(Boolean);
  for (const route of routes) {
    const routeParts = route.split("/").filter(Boolean);
    if (routeParts.length !== hrefParts.length) continue;
    let ok = true;
    for (let i = 0; i < routeParts.length; i++) {
      const rp = routeParts[i];
      const hp = hrefParts[i];
      if (rp.startsWith("[") && rp.endsWith("]")) continue; // dynamic segment matches anything
      if (rp !== hp) {
        ok = false;
        break;
      }
    }
    if (ok) return true;
  }
  return false;
}

const normalizedTargets = allTargets
  .map((t) => ({ ...t, href: normalizeHref(t.raw) }))
  .filter((t) => t.href !== null);

// ---------------------------------------------------------------------------
// 5. Classify: FAIL (broken) vs OK. Orphaned pages.
// ---------------------------------------------------------------------------

// Pages that are intentionally only reachable by typing the URL (founder
// console, internal tooling) — MUST be justified here or the check fails.
const JUSTIFIED_ORPHANS = new Map([
  ["/ops", "Founder-only pilot console; intentionally not linked in nav"],
  ["/chain", "Chain/multi-branch dashboard; reached only by typed URL pending org UX"],
  ["/team", "Team management; reached only by typed URL pending role-gating UX"],
  ["/mobile", "Standalone mobile PWA shell; reached from device home screen"],
  ["/partners", "External partner signup form; linked only from partner emails"],
  ["/ui-kit", "Internal design-system reference page; intentionally not linked in production navigation"],
  ["/onboarding", "Post-registration onboarding wizard; reached only via router.push after signup (ternary arg not statically linkable)"],
]);

const broken = [];
const deadBroken = [];
const ok = [];

for (const t of normalizedTargets) {
  const targetKnown = routes.has(t.href) || routeMatches(t.href) || knownAliases.has(t.href);
  if (targetKnown) {
    ok.push(t);
  } else {
    const fileAbs = join(SRC_DIR, t.file);
    if (reachable.has(fileAbs)) {
      broken.push(t);
    } else {
      deadBroken.push(t); // in an unused component -> cannot ship
    }
  }
}

// Orphaned pages = real pages that nothing in src/ links to (excluding aliases
// already provided by next.config redirects, e.g. /signin -> /login is fine
// because /login is linked from other places anyway). Only references from
// REACHABLE code count, so dead components cannot mask an orphan.
// Dynamic hrefs (e.g. `/findings/${f.id}`) are normalised to their canonical
// route (`/findings/[id]`) so a template-literal link counts as a link.
function canonicalRoute(href) {
  if (routes.has(href)) return href;
  const hrefParts = href.split("/").filter(Boolean);
  for (const route of routes) {
    const routeParts = route.split("/").filter(Boolean);
    if (routeParts.length !== hrefParts.length) continue;
    let ok = true;
    for (let i = 0; i < routeParts.length; i++) {
      const rp = routeParts[i];
      const hp = hrefParts[i];
      if (rp.startsWith("[") && rp.endsWith("]")) continue;
      if (rp !== hp) {
        ok = false;
        break;
      }
    }
    if (ok) return route;
  }
  return null;
}

const linkedRoutes = new Set(
  normalizedTargets
    .filter((t) => {
      const fileAbs = join(SRC_DIR, t.file);
      return reachable.has(fileAbs);
    })
    .map((t) => canonicalRoute(t.href))
    .filter((h) => h !== null)
);
const orphanRoutes = [...routes]
  .filter((r) => !linkedRoutes.has(r) && !knownAliases.has(r))
  .sort();

// ---------------------------------------------------------------------------
// 6. Reporting.
// ---------------------------------------------------------------------------

const summary = {
  pages: routes.size,
  links: normalizedTargets.length,
  broken: broken.length,
  deadBroken: deadBroken.length,
  orphans: orphanRoutes.length,
};

const lines = [];
lines.push("NazmOS Frontend Route/Link Integrity Check");
lines.push("=".repeat(50));
lines.push("");
lines.push("ROUTES (" + routes.size + "):");
for (const r of [...routes].sort()) lines.push("  " + r);
lines.push("");
lines.push("LINK TARGETS (" + normalizedTargets.length + ") -> OK (" + ok.length + ")");
lines.push("");
lines.push("BROKEN LINKS — LIVE CODE (" + broken.length + "):");
if (broken.length === 0) {
  lines.push("  (none)");
} else {
  for (const b of broken) {
    lines.push("  FAIL " + b.href + "  (" + b.file + ":" + b.line + ")  raw=" + b.raw);
  }
}
lines.push("");
lines.push("BROKEN LINKS — DEAD CODE (" + deadBroken.length + ") [warn only]:");
for (const b of deadBroken) {
  lines.push("  DEAD " + b.href + "  (" + b.file + ":" + b.line + ")");
}
lines.push("");
lines.push("ORPHANED PAGES (" + orphanRoutes.length + "):");
for (const r of orphanRoutes) {
  const justified = JUSTIFIED_ORPHANS.get(r);
  lines.push("  " + r + (justified ? "  [JUSTIFIED] " + justified : "  [UNJUSTIFIED]"));
}
lines.push("");
lines.push("SUMMARY: " + summary.pages + " pages, " + summary.links + " links, " + summary.broken + " live-broken, " + summary.deadBroken + " dead-code-broken, " + summary.orphans + " orphaned");

const report = lines.join("\n");
process.stdout.write(report + "\n");

// ---------------------------------------------------------------------------
// 7. Exit code.
// ---------------------------------------------------------------------------

let failCount = broken.length;
const unjustifiedOrphans = orphanRoutes.filter((r) => !JUSTIFIED_ORPHANS.has(r));
failCount += unjustifiedOrphans.length;

if (failCount > 0) {
  process.stderr.write("\nRESULT: FAIL — " + failCount + " unjustified issue(s) (broken links + unjustified orphans)\n");
  process.exit(1);
}
process.stdout.write("\nRESULT: PASS\n");
process.exit(0);
