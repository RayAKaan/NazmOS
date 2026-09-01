// Data-layer types for the landing visualizations.
//
// These structures are deliberately separated from rendering (see §47): they mirror
// real NazmOS domain concepts (graph nodes/edges, agent states, findings, decisions,
// outcomes) so the visual components can later consume live business state without a
// rewrite. All demo values below are deterministic, clearly-sample fixtures — never
// fabricated as live telemetry (§32).

export type NodeType =
  | "product"
  | "branch"
  | "supplier"
  | "inventory"
  | "sales"
  | "margin"
  | "finding"
  | "decision"
  | "action"
  | "outcome";

export interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  /** Optional small caption / sub-label rendered under the node. */
  caption?: string;
  /** Optional numeric value surfaced on hover/interaction. */
  meta?: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  /** Semantic relationship label (e.g. "supplied_by", "generates"). */
  relationship: string;
}

export interface AgentState {
  id: string;
  role: string;
  active: boolean;
  reason?: string;
}

export interface FindingEvidence {
  currentStock?: number;
  sales30d?: number;
  estimatedValue?: number;
  details?: string[];
}

export interface FindingState {
  id: string;
  title: string;
  summary: string;
  importance: "critical" | "warning" | "info";
  evidence: FindingEvidence;
}

export interface DecisionCheck {
  label: string;
  pass: boolean;
  detail: string;
}

export interface DecisionState {
  title: string;
  from: string;
  to: string;
  value: number;
  checks: DecisionCheck[];
}

export interface OutcomeState {
  expected: number;
  actual: number;
  learned: string;
}

// ---------------- Deterministic, clearly-sample demo fixtures ----------------

export const SAMPLE_GRAPH: { nodes: GraphNode[]; edges: GraphEdge[] } = {
  nodes: [
    { id: "arabica", type: "product", label: "Arabic coffee 1kg", caption: "SKU 8841" },
    { id: "riyadh", type: "branch", label: "Branch · Riyadh" },
    { id: "jeddah", type: "branch", label: "Branch · Jeddah" },
    { id: "roaster", type: "supplier", label: "Supplier · Roastery" },
    { id: "stock", type: "inventory", label: "Stock on hand", caption: "142 units" },
    { id: "sales", type: "sales", label: "30-day sales", caption: "96 sold" },
    { id: "margin", type: "margin", label: "Gross margin", caption: "31%" },
    { id: "finding", type: "finding", label: "Overstock risk", caption: "Estimated SAR 27,400" },
    { id: "decision", type: "decision", label: "Decision gate" },
    { id: "outcome", type: "outcome", label: "Realized recovery", caption: "SAR 8,600" },
  ],
  edges: [
    { source: "arabica", target: "roaster", relationship: "supplied_by" },
    { source: "arabica", target: "riyadh", relationship: "stocked_at" },
    { source: "arabica", target: "jeddah", relationship: "stocked_at" },
    { source: "arabica", target: "sales", relationship: "generates" },
    { source: "arabica", target: "margin", relationship: "affects" },
    { source: "sales", target: "stock", relationship: "draws_down" },
    { source: "stock", target: "finding", relationship: "reveals" },
    { source: "finding", target: "decision", relationship: "routes_to" },
    { source: "decision", target: "outcome", relationship: "resolves_to" },
  ],
};

export const SAMPLE_FINDINGS: FindingState[] = [
  {
    id: "overstock",
    title: "Overstock risk — Riyadh",
    summary:
      "Riyadh holds 58 units of Arabic coffee 1kg with 8 days of stock cover. Jeddah is out and reorders from the same roastery weekly.",
    importance: "warning",
    evidence: {
      currentStock: 58,
      sales30d: 96,
      estimatedValue: 27400,
      details: ["58 units on hand", "96 sold in 30 days", "Estimated value SAR 27,400"],
    },
  },
];

export const SAMPLE_DECISION: DecisionState = {
  title: "Transfer inventory",
  from: "Branch · Riyadh",
  to: "Branch · Jeddah",
  value: 8600,
  checks: [
    { label: "Evidence", pass: true, detail: "Overstock cover 8d vs. 3d demand" },
    { label: "Constraints", pass: true, detail: "Within transfer budget" },
    { label: "Financial", pass: true, detail: "Net recovery SAR 8,600" },
    { label: "Risk", pass: true, detail: "No stockout left behind" },
  ],
};

export const SAMPLE_OUTCOME: OutcomeState = {
  expected: 8600,
  actual: 8600,
  learned:
    "Local transfer beat reorder lead time by 11 days. NazmOS recorded the outcome in business memory.",
};

export const SAMPLE_AGENTS: AgentState[] = [
  { id: "inventory", role: "Inventory", active: true, reason: "Overstock cover breached" },
  { id: "finance", role: "Finance", active: true, reason: "Margin + recovery impact" },
  { id: "recovery", role: "Recovery", active: true, reason: "Actionable cash recovery" },
  { id: "procurement", role: "Procurement", active: false, reason: "No PO exceeded" },
  { id: "pricing", role: "Pricing", active: false, reason: "Price within band" },
  { id: "suppliers", role: "Suppliers", active: false, reason: "Supplier SLA stable" },
];

/** The signature loop stages (§16). Ordered; becomes a subtle continuous loop. */
export const SIGNATURE_LOOP = [
  "OBSERVE",
  "UNDERSTAND",
  "ANALYZE",
  "RECOMMEND",
  "ACT",
  "MEASURE",
  "LEARN",
] as const;

/** Free-audit processing stages (§8, §39). Map to honest application states. */
export const AUDIT_STAGES = [
  { id: "read", label: "Reading files" },
  { id: "columns", label: "Finding columns" },
  { id: "normalize", label: "Normalizing data" },
  { id: "match", label: "Matching products" },
  { id: "context", label: "Building business context" },
  { id: "audit", label: "Running audit" },
  { id: "findings", label: "Preparing findings" },
] as const;
