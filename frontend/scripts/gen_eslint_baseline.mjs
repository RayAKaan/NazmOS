// scripts/gen_eslint_baseline.mjs
// Runs the design-system ESLint rules over src/** with NO baseline and writes the full
// current violation set to design-tokens/eslint-rule-baseline.json.
// The main eslint.config.mjs suppresses exactly these entries, so `npm run lint` fails
// only on NEW raw-color / destructive-without-action violations.
// Run: node scripts/gen_eslint_baseline.mjs
import { ESLint } from "eslint";
import { readFileSync, writeFileSync } from "fs";
import { join, relative, sep } from "path";

import noRawColor from "./eslint-rules/no-raw-color.cjs";
import destructiveNeedsAction from "./eslint-rules/destructive-needs-action.cjs";
import tsParser from "@typescript-eslint/parser";

const ROOT = join(import.meta.dirname, "..");

const eslint = new ESLint({
  overrideConfigFile: true,
  cwd: ROOT,
  overrideConfig: [
    {
      files: ["src/**/*.{js,jsx,ts,tsx}"],
      languageOptions: {
        parser: tsParser,
        parserOptions: { ecmaVersion: "latest", sourceType: "module", ecmaFeatures: { jsx: true } },
      },
      plugins: {
        "design-system": {
          rules: { "no-raw-color": noRawColor, "destructive-needs-action": destructiveNeedsAction },
        },
      },
      rules: {
        "design-system/no-raw-color": "error",
        "design-system/destructive-needs-action": "error",
      },
    },
    { ignores: [".next/**", "node_modules/**", "out/**", "coverage/**", "next-env.d.ts"] },
  ],
});

const results = await eslint.lintFiles(["src/**/*.{js,jsx,ts,tsx}"]);

const buckets = { "no-raw-color": [], "destructive-needs-action": [] };
for (const r of results) {
  const rel = relative(ROOT, r.filePath).split(sep).join("/");
  for (const m of r.messages) {
    if (m.ruleId === "design-system/no-raw-color") buckets["no-raw-color"].push(`${rel}:${m.line}`);
    if (m.ruleId === "design-system/destructive-needs-action")
      buckets["destructive-needs-action"].push(`${rel}:${m.line}`);
  }
}
for (const key of Object.keys(buckets)) {
  buckets[key] = Array.from(new Set(buckets[key])).sort();
}

const out = {
  $schema: "./eslint-rule-baseline.schema.json",
  generatedAt: new Date().toISOString().slice(0, 10),
  generator: "scripts/gen_eslint_baseline.mjs",
  ...buckets,
};

writeFileSync(join(ROOT, "design-tokens", "eslint-rule-baseline.json"), JSON.stringify(out, null, 2) + "\n");

console.log(
  `[gen_eslint_baseline] no-raw-color: ${buckets["no-raw-color"].length}, destructive-needs-action: ${buckets["destructive-needs-action"].length}`
);
