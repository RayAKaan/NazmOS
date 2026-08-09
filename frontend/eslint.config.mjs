import nextVitals from "eslint-config-next/core-web-vitals";
import { createRequire } from "module";

const require = createRequire(import.meta.url);

// Design-system enforcement (B0.6). Baseline = design-tokens/eslint-rule-baseline.json
// (regenerate with `node scripts/gen_eslint_baseline.mjs`). Every entry in the baseline
// is grandfathered; `npm run lint` fails on NEW raw-color / destructive-without-action
// violations. Migrating screens shrinks the baseline toward zero.
const noRawColor = require("./scripts/eslint-rules/no-raw-color.cjs");
const destructiveNeedsAction = require("./scripts/eslint-rules/destructive-needs-action.cjs");
const baseline = require("./design-tokens/eslint-rule-baseline.json");

const eslintConfig = [
  ...nextVitals,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "out/**",
      "coverage/**",
      "next-env.d.ts",
    ],
  },
  {
    files: ["src/**/*.{js,jsx,ts,tsx}"],
    plugins: {
      "design-system": {
        rules: {
          "no-raw-color": noRawColor,
          "destructive-needs-action": destructiveNeedsAction,
        },
      },
    },
    rules: {
      "design-system/no-raw-color": [
        "error",
        { baseline: baseline["no-raw-color"] },
      ],
      "design-system/destructive-needs-action": [
        "error",
        { baseline: baseline["destructive-needs-action"] },
      ],
    },
  },
  {
    rules: {
      "react/no-unescaped-entities": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/purity": "off",
      "react-hooks/immutability": "off",
      "react-hooks/static-components": "off",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
];

export default eslintConfig;
