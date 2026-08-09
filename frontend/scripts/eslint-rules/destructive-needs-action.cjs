// scripts/eslint-rules/destructive-needs-action.cjs
// Money-psychology rule: any numeric/currency value rendered with a destructive (red) or
// warning (amber) text color MUST have a sibling action control (button/link/onClick/href)
// in the same visual unit (the nearest enclosing JSXElement).
// Option: { baseline: ["path:line", ...] }
const path = require("path");

const DESTRUCTIVE_TEXT = /\btext-(?:destructive|warning|brand-red|brand-amber|red|rose|yellow|amber)(?:-\d{2,3})?(?:\/\d+)?/;
const CURRENCY_OR_DIGIT = /(\d|SAR|USD|EUR|QAR|KWD|BHD|OMR|AED|PTS|₪|\$|£|€)/;

function collectStrings(node, out) {
  if (!node) return;
  if (node.type === "Literal" && typeof node.value === "string") out.push(node.value);
  else if (node.type === "TemplateElement") out.push(node.value.cooked || node.value.raw);
  else {
    for (const key of Object.keys(node)) {
      if (key === "parent" || key === "loc" || key === "range") continue;
      const val = node[key];
      if (Array.isArray(val)) {
        for (const child of val) if (child && typeof child.type === "string") collectStrings(child, out);
      } else if (val && typeof val.type === "string") collectStrings(val, out);
    }
  }
}

function elementName(jsxEl) {
  const name = jsxEl.openingElement && jsxEl.openingElement.name;
  if (name && name.type === "JSXIdentifier") return name.name;
  if (name && name.type === "JSXMemberExpression") {
    let acc = "";
    let cur = name;
    while (cur && cur.type === "JSXMemberExpression") {
      acc = cur.property.name + acc;
      cur = cur.object;
    }
    if (cur && cur.type === "JSXIdentifier") return cur.name + "." + acc;
  }
  return "";
}

function elementAttributes(jsxEl) {
  const attrs = (jsxEl.openingElement && jsxEl.openingElement.attributes) || [];
  return attrs.filter((a) => a.type === "JSXAttribute").map((a) => a.name && a.name.name);
}

// Extract only rendered TEXT content (JSXText + literal expressions), never attribute
// strings (className/style), so digit detection reflects what the user sees, not code.
function collectText(node, out) {
  if (!node) return;
  if (node.type === "JSXText") {
    out.push(node.value);
    return;
  }
  if (node.type === "JSXExpressionContainer") {
    const e = node.expression;
    if (e && e.type === "Literal") out.push(String(e.value));
    return;
  }
  if (node.type === "JSXElement") {
    for (const child of node.children || []) collectText(child, out);
    return;
  }
  for (const key of Object.keys(node)) {
    if (key === "parent" || key === "loc" || key === "range") continue;
    const val = node[key];
    if (Array.isArray(val)) {
      for (const child of val) if (child && typeof child.type === "string") collectText(child, out);
    } else if (val && typeof val.type === "string") collectText(val, out);
  }
}

function hasAction(node) {
  if (!node) return false;
  if (node.type === "JSXElement") {
    const name = elementName(node);
    if (name === "button" || name === "a") return true;
    const attrs = elementAttributes(node);
    if (attrs.includes("onClick") || attrs.includes("href")) return true;
  }
  for (const key of Object.keys(node)) {
    if (key === "parent" || key === "loc" || key === "range") continue;
    const val = node[key];
    if (Array.isArray(val)) {
      for (const child of val) if (child && typeof child.type === "string" && hasAction(child)) return true;
    } else if (val && typeof val.type === "string" && hasAction(val)) return true;
  }
  return false;
}

module.exports = {
  meta: {
    type: "problem",
    docs: { description: "Destructive/warning money values must be paired with an action control" },
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

    const stack = [];

    function walk(node) {
      if (!node) return;
      if (node.type === "JSXElement") {
        stack.push(node);
        const el = node;
        const classAttr = (el.openingElement.attributes || []).find(
          (a) => a.type === "JSXAttribute" && a.name && a.name.name === "className"
        );
        if (classAttr && classAttr.value) {
          const strings = [];
          collectStrings(classAttr.value, strings);
          const isDestructive = strings.some((s) => DESTRUCTIVE_TEXT.test(s));
          if (isDestructive) {
            const text = [];
            collectText(el, text);
            const hasMoney = text.some((s) => CURRENCY_OR_DIGIT.test(s));
            if (hasMoney) {
              const unit = stack[stack.length - 2] || null;
              const unitHasAction = unit ? hasAction(unit) : hasAction(el);
              if (!unitHasAction) {
                const key = filename + ":" + el.openingElement.loc.start.line;
                if (!baseline.has(key)) {
                  context.report({
                    node: el.openingElement,
                    message:
                      "Money value shown in destructive/warning color must be paired with an action control (button/link) in the same card or visual unit.",
                  });
                }
              }
            }
          }
        }
        for (const child of (el.children || [])) walk(child);
        stack.pop();
        return;
      }
      for (const key of Object.keys(node)) {
        if (key === "parent" || key === "loc" || key === "range") continue;
        const val = node[key];
        if (Array.isArray(val)) {
          for (const child of val) if (child && typeof child.type === "string") walk(child);
        } else if (val && typeof val.type === "string") walk(val);
      }
    }

    return {
      Program(node) {
        walk(node);
      },
    };
  },
};
