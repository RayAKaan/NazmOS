import {
  DOMAINS,
  EDGES,
  RELATED,
  NODE_POS,
  computeEmphasis,
  edgeKey,
  mirrorX,
  type Emphasis,
  type NodeId,
  type UniverseState,
} from "../data";
import { INITIAL_STATE, SELECT, universeReducer } from "../UniverseState";

describe("data layout", () => {
  it("keeps audit out of the domain set so it cannot be a focused signal", () => {
    expect(DOMAINS).toHaveLength(5);
    for (const d of DOMAINS) expect(NODE_POS[d]).toBeDefined();
    expect(DOMAINS).not.toContain("audit");
    expect(NODE_POS.audit).toBeDefined();
    expect(NODE_POS.nazmos).toBeDefined();
  });

  it("mirrors x coordinates for RTL without moving y", () => {
    expect(mirrorX(20, false)).toBe(20);
    expect(mirrorX(20, true)).toBe(80);
    expect(mirrorX(50, true)).toBe(50);
    expect(mirrorX(0, true)).toBe(100);
  });

  it("produces symmetric edge keys", () => {
    expect(edgeKey("sales", "demand")).toBe(edgeKey("demand", "sales"));
    expect(edgeKey("nazmos", "inventory")).toBe("inventory|nazmos");
  });

  it("defines five core edges to NazmOS and five secondary edges", () => {
    const core = EDGES.filter((e) => e.kind === "core");
    const secondary = EDGES.filter((e) => e.kind === "secondary");
    expect(core).toHaveLength(5);
    expect(secondary).toHaveLength(5);
    for (const e of core) {
      expect(e).toEqual({ a: "nazmos", b: expect.any(String), kind: "core" });
      expect(DOMAINS).toContain(e.b as never);
    }
    for (const e of secondary) expect(DOMAINS).toContain(e.a as never);
  });

  it("keeps NazmOS as a related node for every focused domain", () => {
    for (const d of DOMAINS) expect(RELATED[d]).toContain("nazmos");
  });
});

describe("computeEmphasis", () => {
  const levels = (m: ReturnType<typeof computeEmphasis>): Partial<Record<NodeId, Emphasis>> =>
    m.nodeLevels;

  it("anchors NazmOS at level 1 in the base universe (spatial anchor)", () => {
    const m = computeEmphasis({ kind: "universe" }, null);
    expect(levels(m).nazmos).toBe(1);
    expect(m.dimmed).toBe(false);
  });

  it("previews a hovered domain and its related nodes at level 1", () => {
    const m = computeEmphasis({ kind: "universe" }, "sales");
    expect(levels(m).sales).toBe(1);
    expect(levels(m).demand).toBe(1);
    expect(levels(m).inventory).toBe(1);
    expect(levels(m).nazmos).toBe(1);
    expect(levels(m).suppliers).toBeUndefined();
    expect(m.edgeLevels[edgeKey("sales", "demand")]).toBe(1);
    expect(m.dimmed).toBe(false);
  });

  it("previews all domains when NazmOS is hovered", () => {
    const m = computeEmphasis({ kind: "universe" }, "nazmos");
    for (const d of DOMAINS) expect(levels(m)[d]).toBe(1);
    expect(levels(m).nazmos).toBe(1);
  });

  it("ignores a hover on the audit node in the explore space", () => {
    const m = computeEmphasis({ kind: "universe" }, "audit");
    expect(levels(m).nazmos).toBe(1); // anchor still present
  });

  it("focuses a domain at level 2 while keeping NazmOS recognizable", () => {
    const m = computeEmphasis({ kind: "domain", domain: "cost" }, null);
    expect(levels(m).cost).toBe(2);
    expect(levels(m).nazmos).toBe(1);
    expect(levels(m).suppliers).toBe(1);
    expect(m.edgeLevels[edgeKey("cost", "nazmos")]).toBe(2);
    expect(m.edgeLevels[edgeKey("cost", "suppliers")]).toBe(2);
    expect(m.dimmed).toBe(false);
  });

  it("converges everything toward NazmOS in the nazmos state", () => {
    const m = computeEmphasis({ kind: "nazmos" }, null);
    expect(levels(m).nazmos).toBe(2);
    for (const d of DOMAINS) expect(levels(m)[d]).toBe(1);
    expect(m.edgeLevels[edgeKey("nazmos", "sales")]).toBe(2);
    expect(m.edgeLevels[edgeKey("demand", "inventory")]).toBe(1);
    expect(m.dimmed).toBe(false);
  });

  it("dims the system behind the company message (NazmOS absent)", () => {
    const m = computeEmphasis({ kind: "company" }, null);
    expect(m.dimmed).toBe(true);
    expect(levels(m).nazmos).toBeUndefined();
    for (const d of DOMAINS) expect(levels(m)[d]).toBe(0);
    expect(m.edgeLevels[edgeKey("nazmos", "demand")]).toBe(0);
  });

  it("dims the system behind the audit but never removes NazmOS", () => {
    const m = computeEmphasis({ kind: "audit" }, null);
    expect(m.dimmed).toBe(true);
    expect(levels(m).nazmos).toBe(1);
    for (const d of DOMAINS) expect(levels(m)[d]).toBe(0);
    expect(m.edgeLevels[edgeKey("nazmos", "demand")]).toBe(1);
    expect(m.edgeLevels[edgeKey("sales", "inventory")]).toBe(0);
  });
});

describe("universeReducer", () => {
  const dom: UniverseState = { kind: "domain", domain: "sales" };
  const company: UniverseState = { kind: "company" };
  const nazmos: UniverseState = { kind: "nazmos" };
  const audit: UniverseState = { kind: "audit" };

  it("starts in the explore space", () => {
    expect(INITIAL_STATE).toEqual({ kind: "universe" });
  });

  it("opens a domain focus only from the explore space", () => {
    expect(universeReducer(INITIAL_STATE, SELECT("sales"))).toEqual({ kind: "domain", domain: "sales" });
    expect(universeReducer(dom, SELECT("inventory"))).toBe(dom);
    expect(universeReducer(nazmos, SELECT("cost"))).toBe(nazmos);
    expect(universeReducer(audit, SELECT("demand"))).toBe(audit);
  });

  it("routes audit and nazmos selection from any state", () => {
    expect(universeReducer(INITIAL_STATE, SELECT("audit"))).toEqual(audit);
    expect(universeReducer(dom, SELECT("audit"))).toEqual(audit);
    expect(universeReducer(INITIAL_STATE, SELECT("nazmos"))).toEqual(nazmos);
    expect(universeReducer(dom, SELECT("nazmos"))).toEqual(nazmos);
  });

  it("rejects an unknown node id without changing state", () => {
    const before = INITIAL_STATE;
    const after = universeReducer(before, { type: "SELECT", node: "nope" as NodeId });
    expect(after).toBe(before);
  });

  it("progresses toward the audit via TO_NAZMOS and TO_AUDIT", () => {
    expect(universeReducer(dom, { type: "TO_NAZMOS" })).toEqual(nazmos);
    expect(universeReducer(nazmos, { type: "TO_AUDIT" })).toEqual(audit);
    expect(universeReducer(INITIAL_STATE, { type: "TO_AUDIT" })).toEqual(audit);
  });

  it("enters the company state from any state via TO_COMPANY", () => {
    expect(universeReducer(INITIAL_STATE, { type: "TO_COMPANY" })).toEqual(company);
    expect(universeReducer(dom, { type: "TO_COMPANY" })).toEqual(company);
    expect(universeReducer(nazmos, { type: "TO_COMPANY" })).toEqual(company);
  });

  it("returns the same reference for idempotent transitions", () => {
    expect(universeReducer(nazmos, { type: "TO_NAZMOS" })).toBe(nazmos);
    expect(universeReducer(company, { type: "TO_COMPANY" })).toBe(company);
    expect(universeReducer(INITIAL_STATE, { type: "RESET" })).toBe(INITIAL_STATE);
    expect(universeReducer(INITIAL_STATE, { type: "BACK" })).toBe(INITIAL_STATE);
  });

  it("walks BACK along the exact reverse path", () => {
    expect(universeReducer(dom, { type: "BACK" })).toEqual(INITIAL_STATE);
    expect(universeReducer(company, { type: "BACK" })).toEqual(INITIAL_STATE);
    expect(universeReducer(nazmos, { type: "BACK" })).toEqual(INITIAL_STATE);
    expect(universeReducer(audit, { type: "BACK" })).toEqual(nazmos);
    expect(universeReducer(universeReducer(audit, { type: "BACK" }), { type: "BACK" })).toEqual(
      INITIAL_STATE,
    );
  });
});