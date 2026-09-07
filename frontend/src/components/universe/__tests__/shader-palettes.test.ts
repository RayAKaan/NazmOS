import { PALETTES, PARAMS, STATE_MODIFIERS, type ShaderTheme } from "../ShaderBackground";

const THEMES: ShaderTheme[] = ["dark", "light"];

describe("shader palettes — two first-class worlds, one engine", () => {
  it("defines both themes with an identical 8-colour RGB ramp structure", () => {
    for (const theme of THEMES) {
      expect(PALETTES[theme]).toHaveLength(8);
      for (const c of PALETTES[theme]) {
        expect(c).toHaveLength(3);
        for (const v of c) {
          expect(v).toBeGreaterThanOrEqual(0);
          expect(v).toBeLessThanOrEqual(1);
        }
      }
    }
  });

  it("keeps the dominant colour on the histogram-centre slot (index 3)", () => {
    // Dark world: the field centre must render obsidian, not teal — otherwise
    // the teal usage balloons past the ~15% budget (spec §27 budget map).
    expect(Math.max(...PALETTES.dark[3])).toBeLessThanOrEqual(0.05);
    // Light world: the field centre is the warm pearl ivory core (~60% ivory).
    expect(Math.min(...PALETTES.light[3])).toBeGreaterThanOrEqual(0.89);
  });

  it("gives gold its own upper band in both worlds", () => {
    // Gold lives at indices 5–7 as a real material (spec §22 §66). It must be
    // dark enough to read as an object against obsidian AND against ivory.
    const darkGold = PALETTES.dark[6];
    const lightGold = PALETTES.light[6];
    // warm, orange-gold hue in both ramps (R clearly above B, G between).
    for (const g of [darkGold, lightGold]) {
      expect(g[0]).toBeGreaterThan(g[1]);
      expect(g[1]).toBeGreaterThan(g[2]);
    }
    // In dark the gold sits in the upper band (brightens above the obsidian
    // floor); in light it is deeper than the ivory core so it stays visible.
    const darkLuma = 0.299 * darkGold[0] + 0.587 * darkGold[1] + 0.114 * darkGold[2];
    const lightLuma = 0.299 * lightGold[0] + 0.587 * lightGold[1] + 0.114 * lightGold[2];
    expect(darkLuma).toBeGreaterThan(0.4);
    expect(lightLuma).toBeLessThan(0.7);
  });

  it("reaches ivory only at the rare peak of the dark ramp", () => {
    expect(Math.min(...PALETTES.dark[7])).toBeGreaterThanOrEqual(0.8);
  });

  it("shares a complete param contract across themes (identical keys)", () => {
    const darkKeys = Object.keys(PARAMS.dark).sort();
    const lightKeys = Object.keys(PARAMS.light).sort();
    expect(lightKeys).toEqual(darkKeys);
  });

  it("tunes the world-per-theme register (dark heavier, light airier)", () => {
    expect(PARAMS.dark.vignette).toBeGreaterThan(PARAMS.light.vignette);
    expect(PARAMS.dark.saturation).toBeGreaterThan(PARAMS.light.saturation);
    // Both are silent, slow motion — time is in one register.
    expect(PARAMS.dark.timeScale).toBeCloseTo(PARAMS.light.timeScale, 3);
    expect(PARAMS.dark.colorCount).toBe(8);
    expect(PARAMS.light.colorCount).toBe(8);
  });

  it("applies only valid param keys in state modifiers (subset of ShaderParams)", () => {
    const paramKeys = new Set(Object.keys(PARAMS.dark));
    for (const [state, mod] of Object.entries(STATE_MODIFIERS)) {
      expect(["universe", "domain", "company", "nazmos", "audit"]).toContain(state);
      for (const k of Object.keys(mod)) {
        expect(paramKeys.has(k)).toBe(true);
      }
    }
  });

  it("does not override timeScale in any state modifier (animation must stay in one register)", () => {
    for (const [state, mod] of Object.entries(STATE_MODIFIERS)) {
      if ("timeScale" in mod) {
        throw new Error(`STATE_MODIFIERS.${state} must not override timeScale`);
      }
    }
  });
});