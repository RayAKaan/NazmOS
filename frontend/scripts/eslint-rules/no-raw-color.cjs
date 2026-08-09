// scripts/eslint-rules/no-raw-color.cjs
// Flags raw color literals (hex, color functions, named Tailwind palette classes,
// arbitrary-value color classes) in JSX className/style attributes.
// Option: { baseline: ["path:line", ...] } - grandfathered entries are not reported.
const path = require("path");

const HEX = /#[0-9a-fA-F]{3,8}\b/;
const COLOR_FN = /\b(?:rgb|rgba|hsl|hsla|oklch|oklab|hwb|lab|lch|color)\(/;
const PREFIX =
  "(?:text|bg|border|ring|from|via|to|fill|stroke|accent|outline|divide|shadow|caret|placeholder|decoration|selection|file|mark)";
const PALETTE =
  "white|black|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone";
const TW_COLOR_CLASS = new RegExp(
  "\\b" + PREFIX + "-(" + PALETTE + ")(?:-\\d{2,3})?(?:\\/\\[?[0-9.]+\\]?)?"
);
const ARB_COLOR_CLASS = new RegExp(
  "\\b" + PREFIX + "-\\[\\s*(?:#|(?:rgb|rgba|hsl|hsla|oklch|oklab|hwb|lab|lch)\\()"
);

function detect(str) {
  const found = new Set();
  for (const token of str.split(/\s+/)) {
    if (HEX.test(token)) found.add(token);
    else if (COLOR_FN.test(token)) found.add(token);
    else if (TW_COLOR_CLASS.test(token)) found.add(token);
    else if (ARB_COLOR_CLASS.test(token)) found.add(token);
  }
  return Array.from(found);
}

function collectStrings(node, out) {
  if (!node) return;
  if (node.type === "Literal" && typeof node.value === "string") {
    out.push(node.value);
  } else if (node.type === "TemplateElement") {
    out.push(node.value.cooked || node.value.raw);
  } else {
    for (const key of Object.keys(node)) {
      if (key === "parent" || key === "loc" || key === "range") continue;
      const val = node[key];
      if (Array.isArray(val)) {
        for (const child of val) {
          if (child && typeof child.type === "string") collectStrings(child, out);
        }
      } else if (val && typeof val.type === "string") {
        collectStrings(val, out);
      }
    }
  }
}

module.exports = {
  meta: {
    type: "problem",
    docs: { description: "No raw color literals outside design-tokens/tokens.json" },
    schema: [
      {
        type: "object",
        properties: { baseline: { type: "array", items: { type: "string" } } },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const baseline = new Set((context.options[0] && context.options[0].baseline) || []);
    const filename = path
      .relative(process.cwd(), context.getFilename())
      .split(path.sep)
      .join("/");

    function checkAttribute(attr) {
      if (!attr.value) return;
      const strings = [];
      collectStrings(attr.value, strings);
      const offenders = [];
      for (const s of strings) offenders.push(...detect(s));
      if (!offenders.length) return;
      const key = filename + ":" + attr.loc.start.line;
      if (baseline.has(key)) return;
      context.report({
        node: attr,
        message: "Raw color literal(s) must be tokens: {{tokens}} (add to design-tokens/tokens.json and use a token utility)",
        data: { tokens: Array.from(new Set(offenders)).slice(0, 5).join(", ") },
      });
    }

    return {
      JSXAttribute(node) {
        if (node.name && (node.name.name === "className" || node.name.name === "style")) {
          checkAttribute(node);
        }
      },
    };
  },
};
