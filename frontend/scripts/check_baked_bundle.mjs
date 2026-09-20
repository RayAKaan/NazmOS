#!/usr/bin/env node
/**
 * check_baked_bundle.mjs
 *
 * Post-build proof for the NazmOS frontend build chain (FIX 3):
 *   1. The production-shaped build must NOT bake the dev backend origin
 *      (localhost:8000) anywhere in the .next output — neither in the
 *      client bundle nor the server bundle / routes manifest. Next.config
 *      rewrites fall back to `http://localhost:8000` only when API_URL is
 *      unset; the deploy-shaped .env always sets it, so a hit here means the
 *      chain silently regressed to defaults.
 *   2. A server-only secret (canary) must NEVER appear in the client bundle
 *      (.next/static). Next.js only inlines NEXT_PUBLIC_* env vars client-side;
 *      this guard fail-fast proves the discipline is still held regardless of
 *      which vars happened to be referenced from client code.
 *
 * Exit codes: 0 = clean, 1 = FAIL (at least one class of hit), 2 = internal.
 *
 * Usage:
 *   node scripts/check_baked_bundle.mjs            # default canary + localhost:8000
 *   node scripts/check_baked_bundle.mjs --canary <value> --forbidden <origin> [--forbidden <origin>]
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const FRONTEND_ROOT = resolve(import.meta.dirname, "..");
const NEXT_DIR = join(FRONTEND_ROOT, ".next");

// Shipped artifact roots — mirrors Dockerfile.prod COPY set:
//   .next/standalone -> each image's working dir
//   .next/static     -> ./.next/static
//   public           -> ./public
// plus the server route manifest, which the standalone server reads at runtime.
// Build cache (.next/cache) and dev-only *.map sources are NOT shipped and are
// deliberately excluded — their presence cannot leak anything to a browser.
const SHIPPED_ROOTS = [
  join(NEXT_DIR, "static"),
  join(NEXT_DIR, "standalone"),
  join(FRONTEND_ROOT, "public"),
];
const SHIPPED_FILES = [
  join(NEXT_DIR, "routes-manifest.json"),
  join(NEXT_DIR, "required-server-files.json"),
];
// Files that never ship to browsers but still live under .next: source maps
// carry the original dev-default constant (bff-proxy DEFAULT_API_URL) which is
// a legitimate server-side fallback, never handed to the client bundle.
const EXCLUDE_MATCH = /(^|[\\/])cache[\\/]/;

// Server-only canary: a value we put in the fixed build .env under a
// NON-NEXT_PUBLIC_ key. It must never be inlined into the client bundle.
const DEFAULT_CANARY = "canary-9f7e3b1d-cf4a-4d2c-8b2a-1e0f9a2c7d41";
const DEFAULT_FORBIDDEN = ["http://localhost:8000", "http://127.0.0.1:8000"];

function parseArgs(argv) {
  const args = { canary: DEFAULT_CANARY, forbidden: [...DEFAULT_FORBIDDEN] };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--canary" && argv[i + 1] !== undefined) {
      args.canary = argv[++i];
    } else if (argv[i] === "--forbidden" && argv[i + 1] !== undefined) {
      args.forbidden.push(argv[++i]);
    } else if (argv[i] === "--help") {
      process.stdout.write(
        "check_baked_bundle.mjs  [--canary <value>]  [--forbidden <origin>]...\n"
      );
      process.exit(0);
    }
  }
  return args;
}

function walkFiles(dir, acc = []) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return acc;
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) walkFiles(full, acc);
    else if (!EXCLUDE_MATCH.test(full)) acc.push(full);
  }
  return acc;
}

function grepFiles(files, patterns) {
  const hits = [];
  for (const file of files) {
    let content;
    try {
      content = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    for (const pattern of patterns) {
      if (content.includes(pattern)) {
        hits.push({ file: relative(FRONTEND_ROOT, file), pattern });
      }
    }
  }
  return hits;
}

const args = parseArgs(process.argv.slice(2));

const clientBundleDir = join(NEXT_DIR, "static");
if (!statSync(NEXT_DIR, { throwIfNoEntry: false })) {
  process.stderr.write(`RESULT: FAIL — no .next build output at ${NEXT_DIR}\n`);
  process.exit(1);
}

// Only paths that actually ship in the Docker image run the origin scan.
const shippedFiles = [...SHIPPED_FILES, ...SHIPPED_ROOTS.flatMap((r) => walkFiles(r))];

// The client bundle (browser-delivered JS) runs the canary scan.
const clientFiles = walkFiles(clientBundleDir);

const devOriginHits = grepFiles(shippedFiles, args.forbidden);
const canaryHits = grepFiles(clientFiles, [args.canary]);

const lines = [];
lines.push("NazmOS Frontend Baked-Bundle Guard");
lines.push("=".repeat(50));
lines.push("");
lines.push(`FORBIDDEN DEV ORIGINS: ${args.forbidden.join(", ")}`);
lines.push(`SERVER-ONLY CANARY:    ${args.canary}`);
lines.push(`SHIPPED FILES SCANNED: ${shippedFiles.length}`);
lines.push(`CLIENT BUNDLE FILES:   ${clientFiles.length}`);
lines.push("");
lines.push(`HITS — DEV ORIGIN IN .next OUTPUT (${devOriginHits.length}):`);
if (devOriginHits.length === 0) {
  lines.push("  (none)");
} else {
  for (const h of devOriginHits) lines.push(`  FAIL ${h.file}  contains ${h.pattern}`);
}
lines.push("");
lines.push(`HITS — SERVER-ONLY CANARY IN CLIENT BUNDLE (${canaryHits.length}):`);
if (canaryHits.length === 0) {
  lines.push("  (none)");
} else {
  for (const h of canaryHits) lines.push(`  FAIL ${h.file}  contains ${h.pattern}`);
}
lines.push("");

const failCount = devOriginHits.length + canaryHits.length;
lines.push(`SUMMARY: ${failCount} guard hit(s)`);
process.stdout.write(lines.join("\n") + "\n");

if (failCount > 0) {
  process.stderr.write(
    "\nRESULT: FAIL — a dev origin is baked into the build or a server-only secret\n" +
      "reached the client bundle. Build the frontend with the fixed production-shaped\n" +
      ".env (see ci.yml) rather than bare defaults.\n"
  );
  process.exit(1);
}
process.stdout.write("\nRESULT: PASS\n");
process.exit(0);