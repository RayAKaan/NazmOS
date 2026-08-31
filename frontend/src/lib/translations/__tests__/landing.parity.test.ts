import { en } from "../en";
import { ar } from "../ar";

// Collect every leaf path of a nested dictionary.
function leafPaths(node: unknown, prefix = "", out: string[] = []): string[] {
  if (node === null || typeof node !== "object") {
    out.push(prefix);
    return out;
  }
  for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
    leafPaths(v, prefix ? `${prefix}.${k}` : k, out);
  }
  return out;
}

describe("landing translation parity (EN ↔ AR)", () => {
  const enLanding = (en as Record<string, unknown>).landing as Record<string, unknown>;
  const arLanding = (ar as Record<string, unknown>).landing as Record<string, unknown>;

  it("defines a landing block in both locales", () => {
    expect(enLanding).toBeDefined();
    expect(arLanding).toBeDefined();
  });

  it("has identical key structure between EN and AR", () => {
    const enKeys = leafPaths(enLanding).sort();
    const arKeys = leafPaths(arLanding).sort();
    expect(arKeys).toEqual(enKeys);
  });

  it("ensures no location/token placeholder leaked into copy", () => {
    const all = [...leafPaths(enLanding), ...leafPaths(arLanding)];
    // These are key names, not rendered strings; a placeholder in a *value* matters.
    const enValues = JSON.stringify(enLanding);
    const arValues = JSON.stringify(arLanding);
    for (const needle of ["undefined", "NaN", "image-", "TODO", "lorem"]) {
      expect(enValues.toLowerCase()).not.toContain(needle.toLowerCase());
      expect(arValues.toLowerCase()).not.toContain(needle.toLowerCase());
    }
  });

  it("keeps truth-in-advertising guards (sample/not-certified language)", () => {
    const enText = JSON.stringify(enLanding).toLowerCase();
    expect(enText).toContain("sample");
    expect(enText).toContain("not certified");
    expect(enText).toContain("illustrative");
  });
});
