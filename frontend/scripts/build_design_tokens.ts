// scripts/build_design_tokens.ts
// Single source of truth: design-tokens/tokens.json
// Outputs: src/app/globals.css + tailwind.config.ts (everything color/radius/font/shadow is GENERATED).
// Run: node scripts/build_design_tokens.ts
import { readFileSync, writeFileSync } from "fs";
import { join } from "path";

const ROOT = join(import.meta.dirname, "..");
const tokens: any = JSON.parse(
  readFileSync(join(ROOT, "design-tokens", "tokens.json"), "utf8")
);

const kebab = (s: string) =>
  String(s)
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();

const hasAlpha = (v: string) => v.includes("/");
const twValue = (name: string, val: string) =>
  hasAlpha(val)
    ? `var(--${name})`
    : `oklch(var(--${name}) / <alpha-value>)`;

const canonical = tokens.colors as Record<string, { light: string; dark: string }>;
const legacy = tokens.legacyLiteralColors as Record<string, Record<string, string>>;

// ----- tailwind colors -----
const PAIRS = ["card", "popover", "primary", "secondary", "destructive", "muted", "warning", "success"];

const colors: Record<string, any> = {};

for (const p of PAIRS) {
  colors[p] = {
    DEFAULT: twValue(p, canonical[p].dark),
    foreground: twValue(`${p}-foreground`, canonical[`${p}-foreground`].dark),
  };
}

// accent is special: DEFAULT keeps the legacy gold (current behavior), `surface`
// exposes the canonical hover surface, and the remaining legacy accent keys resolve
// through --accent-* variables.
const accentLegacy = legacy.accent;
const accentKeys = Object.keys(accentLegacy).filter(
  (k) => k !== "DEFAULT" && k !== "foreground"
);
colors.accent = {
  DEFAULT: twValue("accent-primary", accentLegacy.DEFAULT),
  foreground: twValue("accent-foreground", canonical["accent-foreground"].dark),
  surface: twValue("accent", canonical.accent.dark),
};
for (const k of accentKeys) {
  colors.accent[kebab(k)] = twValue(`accent-${kebab(k)}`, accentLegacy[k]);
}

// standalone canonical singles
const SINGLES = [
  "background", "foreground", "input", "ring", "border",
  "success-bright",
  "chart-1", "chart-2", "chart-3", "chart-4", "chart-5", "chart-grid",
  "surface-hover", "overlay", "glass", "glass-border",
];
for (const s of SINGLES) {
  colors[s] = twValue(s, canonical[s].dark);
}

// legacy namespaces (keep every existing class resolving)
const LEGACY_NS = ["brand", "status", "navy", "bg", "text", "intelligence", "chat"];
for (const ns of LEGACY_NS) {
  const obj: Record<string, string> = {};
  for (const [k, v] of Object.entries(legacy[ns])) {
    const name = k === "DEFAULT" ? ns : `${ns}-${kebab(k)}`;
    obj[k === "DEFAULT" ? "DEFAULT" : kebab(k)] = twValue(name, v);
  }
  colors[ns] = obj;
}

// top-level border-primary / border-secondary (current class names)
colors["border-primary"] = twValue("border-literal-primary", legacy.borderLiteral.primary);
colors["border-secondary"] = twValue("border-literal-secondary", legacy.borderLiteral.secondary);

// whatsapp: legacy namespace is the full current surface
colors.whatsapp = {
  DEFAULT: "var(--whatsapp)",
};
for (const k of Object.keys(legacy.whatsapp)) {
  if (k === "DEFAULT") continue;
  colors.whatsapp[kebab(k)] = twValue(`whatsapp-${kebab(k)}`, legacy.whatsapp[k]);
}

// ----- tailwind radius / fonts / shadows -----
const radius: Record<string, string> = {};
for (const [k, v] of Object.entries(tokens.radius as Record<string, string>)) {
  radius[kebab(k)] = v;
}

const fontFamily = tokens.typography.fontFamily as Record<string, string[]>;

const shadowMap: Record<string, string> = {};
for (const k of ["card", "glow-gold", "glow-teal"]) {
  shadowMap[kebab(k)] = (tokens.shadows as Record<string, string>)[k];
}

// ----- preserved static config -----
const config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      colors,
      borderRadius: radius,
      fontFamily,
      boxShadow: shadowMap,
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "fade-in-up": { "0%": { opacity: "0", transform: "translateY(20px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        "fade-in-down": { "0%": { opacity: "0", transform: "translateY(-20px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        "slide-in-left": { "0%": { opacity: "0", transform: "translateX(-20px)" }, "100%": { opacity: "1", transform: "translateX(0)" } },
        "slide-in-right": { "0%": { opacity: "0", transform: "translateX(20px)" }, "100%": { opacity: "1", transform: "translateX(0)" } },
        "scale-in": { "0%": { opacity: "0", transform: "scale(0.95)" }, "100%": { opacity: "1", transform: "scale(1)" } },
        float: { "0%, 100%": { transform: "translateY(0px)" }, "50%": { transform: "translateY(-10px)" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.5s ease-out forwards",
        "fade-in-up": "fadeInUp 0.5s ease-out forwards",
        "fade-in-down": "fadeInDown 0.5s ease-out forwards",
        "slide-in-left": "slideInLeft 0.5s ease-out forwards",
        "slide-in-right": "slideInRight 0.5s ease-out forwards",
        "scale-in": "scaleIn 0.3s ease-out forwards",
        float: "float 6s ease-in-out infinite",
      },
    },
  },
  // plugins assigned after stringify (require is a runtime import)
  plugins: [] as string[],
};

// ----- globals.css -----
function cssVarsFromCanonical(mode: "light" | "dark"): string {
  const lines: string[] = [];
  for (const [name, def] of Object.entries(canonical)) {
    const key = kebab(name);
    if (name === "whatsapp") continue; // legacy namespace wins
    lines.push(`  --${key}: ${def[mode]};`);
  }
  return lines.join("\n");
}
function cssVarsFromLegacy(): string {
  const lines: string[] = [];
  for (const [ns, defs0] of Object.entries(legacy)) {
    if (ns === "description") continue;
    const defs = defs0 as Record<string, string>;
    const nsK = kebab(ns);
    for (const [k, v] of Object.entries(defs)) {
      if (ns === "accent" && (k === "DEFAULT" || k === "foreground")) continue;
      const name = k === "DEFAULT" ? nsK : `${nsK}-${kebab(k)}`;
      lines.push(`  --${name}: ${v};`);
    }
  }
  return lines.join("\n");
}

const staticCss = `@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    color-scheme: light;
${cssVarsFromCanonical("light").replace(/^/gm, "    ")}
    --radius: ${tokens.radius.DEFAULT};

    /* Local/system font stack: avoids build-time Google Font fetch failures. */
    --font-serif: Georgia, Cambria, "Times New Roman", serif;
    --font-sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
    --font-arabic: "IBM Plex Sans Arabic", "Noto Kufi Arabic", Arial, sans-serif;
  }

  .dark {
    color-scheme: dark;
${cssVarsFromCanonical("dark").replace(/^/gm, "    ")}
  }

  /* Legacy literal aliases (versioned in tokens.json) - resolve in both modes. */
  :root, .dark {
${cssVarsFromLegacy().replace(/^/gm, "    ")}
  }
}

@layer base {
  * {
    @apply border-border;
  }

  body {
    @apply bg-background text-foreground;
    font-feature-settings: "rlig" 1, "calt" 1;
  }

  html {
    scroll-behavior: smooth;
  }
}

@layer utilities {
  .grain {
    position: relative;
  }

  .grain::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
    opacity: 0.03;
    pointer-events: none;
    z-index: 1;
  }

  .text-balance {
    text-wrap: balance;
  }

  .shadow-subtle {
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.3), 0 0 0 1px rgba(255, 255, 255, 0.02);
  }

  .shadow-glow {
    box-shadow: 0 0 20px rgba(212, 165, 116, 0.15);
  }

  .shadow-glow-lg {
    box-shadow: 0 0 40px rgba(212, 165, 116, 0.2);
  }

  .shadow-glow-teal {
    box-shadow: 0 0 24px rgba(20, 184, 166, 0.15);
  }

  .shadow-glow-teal-lg {
    box-shadow: 0 0 40px rgba(20, 184, 166, 0.22);
  }

  .border-brand-teal {
    border-color: var(--brand-teal);
  }

  .text-brand-teal {
    color: var(--brand-teal);
  }

  .bg-brand-teal {
    background-color: var(--brand-teal);
  }

  .prose-intelligence {
    @apply text-sm leading-6 text-text-secondary;
  }

  .prose-intelligence p {
    @apply mb-3 last:mb-0;
  }

  .prose-intelligence strong {
    @apply text-text-primary font-semibold;
  }

  .prose-intelligence ul {
    @apply list-disc pl-5 space-y-1;
  }

  .focus-ring {
    @apply focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary;
  }
}
`;

// ----- write -----
const configFile = `import type { Config } from "tailwindcss";

// AUTO-GENERATED from design-tokens/tokens.json via scripts/build_design_tokens.ts - DO NOT EDIT.
const config: Config = ${JSON.stringify(config, null, 2)};
config.plugins = [require("tailwindcss-animate")];

export default config;
`;

writeFileSync(join(ROOT, "tailwind.config.ts"), configFile);
writeFileSync(join(ROOT, "src", "app", "globals.css"), staticCss);

console.log(
  `[build_design_tokens] wrote tailwind.config.ts and src/app/globals.css` +
    ` (${Object.keys(colors).length} color groups, ${Object.keys(radius).length} radii, ${Object.keys(shadowMap).length} shadows)`
);
