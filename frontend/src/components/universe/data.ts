export type DomainId = "sales" | "inventory" | "demand" | "suppliers" | "cost";

export type NodeId = DomainId | "nazmos" | "audit";

export type UniverseStateKind = "universe" | "domain" | "company" | "nazmos" | "audit";

export interface UniverseState {
  kind: UniverseStateKind;
  domain?: DomainId;
}

// Layout in a 0..100 coordinate space (mirrored for RTL at render time).
export const NODE_POS: Record<NodeId, { x: number; y: number }> = {
  nazmos: { x: 50, y: 58 },
  demand: { x: 50, y: 12 },
  suppliers: { x: 22, y: 36 },
  sales: { x: 78, y: 36 },
  inventory: { x: 28, y: 86 },
  cost: { x: 72, y: 86 },
  audit: { x: 50, y: 50 },
};

export const DOMAINS: DomainId[] = ["demand", "suppliers", "sales", "inventory", "cost"];

export interface EdgeDef {
  a: NodeId;
  b: NodeId;
  kind: "core" | "secondary";
}

// The relationship network. CORE edges run between every signal and NazmOS —
// they are the backbone that must never disappear. SECONDARY edges surface the
// dependencies between signals and light up when a signal is focused.
export const EDGES: EdgeDef[] = [
  { a: "nazmos", b: "demand", kind: "core" },
  { a: "nazmos", b: "suppliers", kind: "core" },
  { a: "nazmos", b: "sales", kind: "core" },
  { a: "nazmos", b: "inventory", kind: "core" },
  { a: "nazmos", b: "cost", kind: "core" },
  { a: "sales", b: "demand", kind: "secondary" },
  { a: "sales", b: "inventory", kind: "secondary" },
  { a: "inventory", b: "suppliers", kind: "secondary" },
  { a: "suppliers", b: "cost", kind: "secondary" },
  { a: "demand", b: "inventory", kind: "secondary" },
];

// Which nodes each domain is related to (used to decide what recedes vs clarifies).
export const RELATED: Record<DomainId, NodeId[]> = {
  sales: ["nazmos", "demand", "inventory"],
  inventory: ["nazmos", "sales", "suppliers"],
  demand: ["nazmos", "sales", "inventory"],
  suppliers: ["nazmos", "inventory", "cost"],
  cost: ["nazmos", "suppliers"],
};

/** Mirror an x coordinate for RTL rendering. */
export function mirrorX(x: number, rtl: boolean): number {
  return rtl ? 100 - x : x;
}

/** Symmetric edge key so focus logic never depends on edge direction. */
export function edgeKey(a: NodeId, b: NodeId): string {
  return [a, b].sort().join("|");
}

export type Emphasis = 0 | 1 | 2;

export interface EmphasisMap {
  nodeLevels: Partial<Record<NodeId, Emphasis>>;
  edgeLevels: Partial<Record<string, Emphasis>>;
  dimmed: boolean;
}

/**
 * Continuity model: the network is never removed from view. A focused signal
 * dominates, its related nodes stay connected, unrelated nodes recede, and
 * NazmOS remains a stable spatial anchor in every state.
 */
export function computeEmphasis(state: UniverseState, hovered: NodeId | null): EmphasisMap {
  const nodeLevels: Partial<Record<NodeId, Emphasis>> = {};
  const edgeLevels: Partial<Record<string, Emphasis>> = {};
  let dimmed = false;

  const set = (n: NodeId, l: Emphasis) => {
    nodeLevels[n] = Math.max(nodeLevels[n] ?? 0, l) as Emphasis;
  };
  const setEdge = (e: EdgeDef, l: Emphasis) => {
    const k = edgeKey(e.a, e.b);
    edgeLevels[k] = Math.max(edgeLevels[k] ?? 0, l) as Emphasis;
  };

  switch (state.kind) {
    case "universe": {
      // NazmOS is the stable spatial anchor in every state — always present,
      // always recognizable. The five signals rest at level 0 around it.
      set("nazmos", 1);
      // Hover behaves like a subtle, non-destructive focus preview.
      if (hovered && hovered !== "audit") {
        set(hovered, 1);
        if (hovered === "nazmos") {
          for (const d of DOMAINS) set(d, 1);
        } else if (DOMAINS.includes(hovered as DomainId)) {
          for (const r of RELATED[hovered as DomainId]) set(r, 1);
        }
        for (const e of EDGES) {
          if (e.a === hovered || e.b === hovered) setEdge(e, 1);
        }
      }
      break;
    }
    case "domain": {
      const dom = state.domain!;
      set(dom, 2);
      for (const r of RELATED[dom]) set(r, 1);
      // Stable spatial anchor: NazmOS always stays recognizable.
      set("nazmos", 1);
      for (const e of EDGES) {
        if (e.a === dom || e.b === dom) setEdge(e, 2);
        else if (e.a === "nazmos" || e.b === "nazmos") setEdge(e, 1);
        else if (RELATED[dom].includes(e.a) || RELATED[dom].includes(e.b)) setEdge(e, 1);
      }
      break;
    }
    case "nazmos": {
      // The convergence hold: all signals pull toward the centre.
      set("nazmos", 2);
      for (const d of DOMAINS) set(d, 1);
      for (const e of EDGES) setEdge(e, e.kind === "core" ? 2 : 1);
      break;
    }
    case "company": {
      // The company message takes the stage; the system recedes to a ghost.
      // NazmOS stays as a faint spatial anchor ('0'), so the surrounding system
      // remains acknowledged but pushed behind the company's words.
      dimmed = true;
      for (const d of DOMAINS) set(d, 0);
      for (const e of EDGES) {
        if (e.a === "nazmos" || e.b === "nazmos") setEdge(e, 0);
      }
      break;
    }
    case "audit": {
      // The audit takes centre stage; the system recedes behind it.
      dimmed = true;
      set("nazmos", 1);
      for (const d of DOMAINS) set(d, 0);
      for (const e of EDGES) setEdge(e, e.a === "nazmos" || e.b === "nazmos" ? 1 : 0);
      break;
    }
  }

  return { nodeLevels, edgeLevels, dimmed };
}