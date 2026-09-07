import { DOMAINS, type DomainId, type NodeId, type UniverseState } from "./data";

export type UniverseAction =
  | { type: "SELECT"; node: NodeId }
  | { type: "TO_COMPANY" }
  | { type: "TO_NAZMOS" }
  | { type: "TO_AUDIT" }
  | { type: "BACK" }
  | { type: "RESET" };

export const INITIAL_STATE: UniverseState = { kind: "universe" };

/** Convenience constructor for the SELECT action. */
export function SELECT(node: NodeId): Extract<UniverseAction, { type: "SELECT" }> {
  return { type: "SELECT", node };
}

/**
 * Finite state machine. The model is deliberately a simple directed flow —
 * the scene may look dense, but the interaction is deterministic:
 *
 *   universe ──select signal──▶ domain
 *   universe ─────────────────▶ nazmos ──▶ audit
 *   domain ──CTA──▶ nazmos     (progression)
 *   domain / nazmos / audit ──ESC──▶ universe
 *
 * There is no arbitrary node-to-node navigation: from a focused domain the
 * only forward move is toward NazmOS, from NazmOS toward the audit.
 */
export function universeReducer(state: UniverseState, action: UniverseAction): UniverseState {
  switch (action.type) {
    case "SELECT": {
      const n = action.node;
      if (n === "audit") return { kind: "audit" };
      if (n === "nazmos") {
        return state.kind === "nazmos" ? state : { kind: "nazmos" };
      }
      const d = n as DomainId;
      if (!DOMAINS.includes(d)) return state;
      // Deterministic: domains focus only from the explore space.
      if (state.kind === "universe") return { kind: "domain", domain: d };
      return state;
    }
    case "TO_COMPANY":
      return state.kind === "company" ? state : { kind: "company" };
    case "TO_NAZMOS":
      return state.kind === "nazmos" ? state : { kind: "nazmos" };
    case "TO_AUDIT":
      return { kind: "audit" };
    case "BACK":
      if (state.kind === "domain") return { kind: "universe" };
      if (state.kind === "company") return { kind: "universe" };
      if (state.kind === "nazmos") return { kind: "universe" };
      if (state.kind === "audit") return { kind: "nazmos" };
      return state;
    case "RESET":
      return state.kind === "universe" ? state : { kind: "universe" };
    default:
      return state;
  }
}