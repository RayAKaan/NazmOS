// scripts/token-migration/migrate.ts
// Phase 3 migrator: exact-literal legacy -> canonical class renamer (mission "single
// semantic token layer"). Reads mapping.json; rewrites legacy className tokens to their
// canonical Tier-2 forms inside src/**/*.{ts,tsx}.
//
// Matching semantics:
//   - WHOLE-TOKEN literal matching only. A token is delimited by any character outside
//     the class charset [A-Za-z0-9_\-/], so `bg-navy-panel` is never rewritten inside
//     `bg-navy-panel-2`. Variant prefixes such as `hover:`, `placeholder:`,
//     `focus-visible:` are part of the mapping key (e.g. key "hover:bg-bg-hover").
//   - Longest-key-first so overlapping legacy names resolve deterministically.
//   - Null-valued mapping entries are prune-only (kept as definitions in tokens.json);
//     they must never be found in src — a run asserts zero occurrences.
//   - Any detected utility naming a legacy namespace (navy/bg/text/status) that has NO
//     mapping entry fails the run (no silent leftovers).
//
// Modes:
//   node scripts/token-migration/migrate.ts                dry-run over ALL src
//   node scripts/token-migration/migrate.ts --batch chain  dry-run scoped to a batch
//   node scripts/token-migration/migrate.ts --batch remaining
//   node scripts/token-migration/migrate.ts --apply --batch chain
//   node scripts/token-migration/migrate.ts --apply --all
//
// Batches mirror the Phase 0 audit report §11 hotspots; anything matched but not listed
// lands in batch 6 (remaining), guaranteeing per-batch totals and a final zero-leftover
// verification in one pass.

import { readFileSync, writeFileSync, readdirSync, statSync } from "fs";
import { join, resolve, relative, sep } from "path";

const ROOT = resolve(import.meta.dirname, "..", "..");
const SRC = join(ROOT, "src");
const MAPPING = JSON.parse(readFileSync(join(import.meta.dirname, "mapping.json"), "utf8"));

const NAMED_BATCHES = [
  {
    name: "chain",
    description: "phase-audit §11 batch 1: chain / integrations / team / settings-autonomy",
    files: [
      "app/(dashboard)/chain/page",
      "app/(dashboard)/integrations/page",
      "app/(dashboard)/team/page",
      "app/(dashboard)/settings/autonomy/page",
    ],
  },
  {
    name: "dashboard",
    description: "phase-audit §11 batch 2: dashboard shell + shared dashboard/ui components",
    files: ["app/(dashboard)/dashboard/page", "components/dashboard", "components/ui"],
  },
  {
    name: "pages",
    description: "phase-audit §11 batch 3: remaining screens, scene components, auth",
    files: [
      "app/(dashboard)/forecast/page",
      "app/(dashboard)/upload/page",
      "app/(dashboard)/feed/page",
      "app/(dashboard)/inventory",
      "app/(dashboard)/suppliers/page",
      "app/(dashboard)/ops/page",
      "app/(dashboard)/orchestrator/page",
      "app/(dashboard)/chat/page",
      "app/(dashboard)/recovery-match/page",
      "app/(dashboard)/findings",
      "app/(dashboard)/weekly-report/page",
      "app/(auth)",
      "app/partners/page",
      "app/mobile/page",
      "app/demo/page",
      "app/terms/page",
      "app/privacy/page",
      "app/ui-kit",
      "components/upload",
      "components/intelligence",
      "components/pilot",
    ],
  },
  {
    name: "money-audit",
    description: "phase-audit §11 batch 4: money-audit scene",
    files: ["app/(dashboard)/money-audit/page", "components/money-audit"],
  },
  {
    name: "landing",
    description: "phase-audit §11 batch 5: public landing, product demo, marketing components",
    files: ["app/page", "app/not-found", "app/product-demo", "components/landing"],
  },
];

const UTIL_PREFIX =
  "(?:hover:|focus:|focus-visible:|active:|group-hover:|group-focus-visible:|placeholder:|peer-hover:)?(?:text|bg|border|divide|from|via|to|placeholder|ring|ring-offset|fill|stroke|caret|decoration|outline|accent|selection|mark|shadow|split)(?:-focus-visible)?-(?:navy|bg|text|status)-[A-Za-z0-9_/-]+";
const VARIANT_PREFIXES = [
  "hover:",
  "focus:",
  "focus-visible:",
  "active:",
  "group-hover:",
  "group-focus-visible:",
  "placeholder:",
  "peer-hover:",
];

interface Rule {
  key: string;
  canonical: string;
  re: RegExp;
}
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const TOKEN_BOUNDARY = "[A-Za-z0-9_/\\-]";

function buildRules(): Rule[] {
  const rules: Rule[] = [];
  for (const [key, value] of Object.entries(MAPPING.tokens)) {
    if (typeof value !== "string" || !value) continue;
    rules.push({ key, canonical: value, re: new RegExp(`(?<!${TOKEN_BOUNDARY})${esc(key)}(?!${TOKEN_BOUNDARY})`, "g") });
  }
  return rules.sort((a, b) => b.key.length - a.key.length);
}
const RULES = buildRules();

const PRUNE_ONLY = Object.entries(MAPPING.tokens)
  .filter(([, v]) => typeof v !== "string")
  .map(([k]) => k);

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".next") continue;
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.(ts|tsx)$/.test(entry) && !entry.endsWith(".d.ts")) out.push(p);
  }
  return out;
}
const srcRel = (p: string) => relative(SRC, p).split(sep).join("/");

function detectsLegacy(line: string): string[] {
  const out: string[] = [];
  const re = new RegExp(UTIL_PREFIX, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) out.push(m[0]);
  return out;
}

interface FileReport {
  path: string;
  changed: boolean;
  lines: { line: number; before: string; after: string }[];
  tokens: Record<string, number>;
  content: string;
}

function migrateFile(abs: string): FileReport {
  const input = readFileSync(abs, "utf8");
  const lines = input.split("\n");
  const rep: FileReport = { path: srcRel(abs), changed: false, lines: [], tokens: {}, content: input };
  for (let i = 0; i < lines.length; i++) {
    const original = lines[i];
    let cur = original;
    for (const rule of RULES) {
      if (rule.re.test(cur)) {
        rule.re.lastIndex = 0;
        const hits = cur.match(rule.re)?.length || 0;
        const next = cur.replace(rule.re, rule.canonical);
        if (next !== cur) {
          cur = next;
          rep.tokens[rule.key] = (rep.tokens[rule.key] || 0) + hits;
        }
      }
    }
    if (cur !== original) {
      rep.changed = true;
      rep.lines.push({ line: i + 1, before: original.trim(), after: cur.trim() });
      lines[i] = cur;
    }
  }
  if (rep.changed) rep.content = lines.join("\n");
  return rep;
}

function batchFor(report: FileReport): string {
  for (const b of NAMED_BATCHES) {
    for (const frag of b.files) {
      if (
        report.path === frag ||
        report.path === frag + ".tsx" ||
        report.path === frag + ".ts" ||
        report.path.startsWith(frag + "/")
      ) {
        return b.name;
      }
    }
  }
  return "remaining";
}

function summarize(files: FileReport[]): boolean {
  const touched = files.filter((f) => f.changed);
  let linesTouched = 0;
  const perToken: Record<string, number> = {};
  const byBatch: Record<string, string[]> = {};
  for (const f of touched) {
    linesTouched += f.lines.length;
    for (const t of Object.keys(f.tokens)) perToken[t] = (perToken[t] || 0) + f.tokens[t];
    const b = batchFor(f);
    (byBatch[b] = byBatch[b] || []).push(f.path);
  }
  console.log(`\n[taken count] ${touched.length} file(s), ${linesTouched} line(s) touched`);
  console.log(`  per-token replacement counts:\n    ${Object.keys(perToken).map((k) => `${k} -> ${perToken[k]}`).join("\n    ")}`);
  for (const b of Object.keys(byBatch).sort()) {
    console.log(`  batch ${b} (${byBatch[b].length} file(s)):`);
    for (const p of byBatch[b]) console.log(`      ${p}`);
  }
  return linesTouched > 0;
}

function verifyNoLeftovers(allFiles: string[]): void {
  let unmapped = 0;
  for (const abs of allFiles) {
    const lines = readFileSync(abs, "utf8").split("\n");
    for (let i = 0; i < lines.length; i++) {
      for (const token of detectsLegacy(lines[i])) {
        const covered =
          MAPPING.tokens[token] !== undefined ||
          VARIANT_PREFIXES.some((p) => MAPPING.tokens[p + token] !== undefined);
        if (!covered) {
          console.error(`UNMAPPED LEGACY ${token} @ ${srcRel(abs)}:${i + 1}: ${lines[i].trim()}`);
          unmapped++;
        }
      }
    }
  }
  if (unmapped > 0) {
    console.error(`FAIL: ${unmapped} unmapped legacy utility(ies) name a legacy namespace.`);
    process.exit(1);
  }
}

function verifyPruneOnlyAbsent(allFiles: string[]): void {
  const hits: string[] = [];
  for (const abs of allFiles) {
    const lines = readFileSync(abs, "utf8").split("\n");
    for (const key of PRUNE_ONLY) {
      const re = new RegExp(`(?<!${TOKEN_BOUNDARY})${esc(key)}(?!${TOKEN_BOUNDARY})`, "g");
      for (let i = 0; i < lines.length; i++) {
        const before = re.test(lines[i]);
        if (before) {
          re.lastIndex = 0;
          hits.push(`${srcRel(abs)}:${i + 1} ${key}`);
        }
      }
    }
  }
  if (hits.length) {
    console.error(`FAIL: prune-only tokens found in src:\n  ${hits.join("\n  ")}`);
    process.exit(1);
  }
}

function main() {
  const args = process.argv.slice(2);
  const apply = args.includes("--apply");
  const all = args.includes("--all");
  const batchIdx = args.indexOf("--batch");
  const batchName = batchIdx >= 0 ? args[batchIdx + 1] : undefined;
  if (batchName && all) {
    console.error("Use either --batch <name> or --all, not both.");
    process.exit(1);
  }

  const files = walk(SRC);
  verifyNoLeftovers(files);
  verifyPruneOnlyAbsent(files);

  const reports: FileReport[] = files.map(migrateFile);

  let scope: FileReport[];
  if (batchName) {
    const b = NAMED_BATCHES.find((x) => x.name === batchName);
    if (!b) {
      console.error(`Unknown batch '${batchName}'. Known: ${NAMED_BATCHES.map((x) => x.name).join(", ")} + remaining`);
      process.exit(1);
    }
    scope = reports.filter((r) => batchFor(r) === batchName);
    console.error(`[${apply ? "APPLY" : "DRY-RUN"}] batch '${batchName}' (${b.description})`);
  } else {
    scope = reports;
    console.error(`[${apply ? "APPLY" : "DRY-RUN"}] all src`);
  }

  if (apply) {
    let written = 0;
    for (const f of scope) {
      if (!f.changed) continue;
      writeFileSync(join(SRC, ...f.path.split("/")), f.content);
      written++;
    }
    console.error(`wrote ${written} file(s).`);
  }
  summarize(scope);
}

main();