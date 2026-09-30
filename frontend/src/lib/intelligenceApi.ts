/**
 * Canonical Intelligence layer contracts + typed client.
 *
 * These types mirror `backend/app/schemas/intelligence.py` exactly, so the
 * frontend consumes the canonical Intelligence pipeline rather than the legacy
 * alternate shapes (dashboard summary / chat reason).
 *
 * Authority: Intelligence understands; it never executes. There is deliberately
 * no execute/predict client here — those endpoints were removed from the API.
 */

import api from "@/lib/api";

/* ── Vocabularies (mirrors the backend Enums) ─────────────────────────────── */

export type FreshnessStatus =
  | "fresh"
  | "stale"
  | "partial"
  | "missing"
  | "conflict"
  | "unknown";

export type SignalSeverity = "info" | "warning" | "critical";

export type SignalStatus =
  | "detected"
  | "confirmed"
  | "acknowledged"
  | "resolved"
  | "expired"
  | "superseded";

export type SupportLevel = "observed" | "supported" | "possible" | "unknown";

/** Potential impact is a planning figure — never recovered cash. */
export type ImpactKind =
  | "potential"
  | "expected"
  | "approved"
  | "executed"
  | "verified";

export type AdvisorySource =
  | "jev"
  | "llm_api"
  | "deterministic_only"
  | "mocked";

export type IntelligenceRunStatus =
  | "running"
  | "completed"
  | "partial"
  | "failed";

/* ── Entities ─────────────────────────────────────────────────────────────── */

export interface BusinessContext {
  business_id: string;
  /** Orbit audit id — the authoritative business state version. */
  state_version: string;
  snapshot_timestamp: string;
  data_freshness: FreshnessStatus;
  data_quality_score: number | null;
  business_type: string;
  health_score: number;
  health_breakdown: Record<string, unknown>;
  exposures: Record<string, unknown>;
  findings: Array<Record<string, unknown>>;
  opportunities: Array<Record<string, unknown>>;
  limitations: Record<string, unknown>;
  historical_metrics: Record<string, unknown>;
  evidence_ids: string[];
  contract_version: string;
}

export interface Signal {
  signal_id: string;
  business_id: string;
  state_version: string;
  signal_type: string;
  domain: string;
  metric: string;
  observed_value: number;
  baseline_value: number;
  baseline_type: string;
  /** Human-readable description of how the baseline was computed. */
  baseline_formula: string;
  deviation: number;
  deviation_percent: number;
  severity: SignalSeverity;
  confidence: number;
  detected_at: string;
  evidence_ids: string[];
  freshness: FreshnessStatus;
  status: SignalStatus;
  detector_version: string;
  detector_name: string;
  fingerprint: string;
}

export interface RootCause {
  root_cause_id: string;
  signal_id: string;
  cause_type: string;
  description: string;
  confidence: number;
  support_level: SupportLevel;
  evidence_ids: string[];
  contributing_factors: string[];
  /** Evidence that argues against this cause — surfaced, never hidden. */
  contradictory_evidence: string[];
  analysis_version: string;
  analyzed_at: string;
}

export interface ImpactEstimate {
  impact_id: string;
  signal_id: string;
  kind: ImpactKind;
  amount_sar: number;
  lower_bound_sar: number;
  upper_bound_sar: number;
  formula: string;
  assumptions: string[];
  confidence: number;
  evidence_ids: string[];
  currency: string;
  period: string;
  calculation_version: string;
  calculated_at: string;
}

export interface ImpactRef {
  amount_sar: number;
  kind: ImpactKind;
  formula: string;
  assumptions: string[];
}

export interface AdvisoryResult {
  source: AdvisorySource;
  confidence: number;
  reasoning: string;
  suggested_action: string | null;
  alternative_action: string | null;
  challenge: boolean;
  risk_flags: string[];
  evidence_ids: string[];
  latency_ms: number;
  jev_consulted: boolean;
}

export interface Recommendation {
  recommendation_id: string;
  business_id: string;
  state_version: string;
  signal_ids: string[];
  root_cause_ids: string[];
  evidence_ids: string[];
  action_type: string;
  rationale: string;
  potential_impact: ImpactRef | null;
  expected_impact: ImpactRef | null;
  confidence: number;
  urgency: string;
  risk: string;
  reversibility: string;
  affected_resources: string[];
  constraints: Record<string, unknown>;
  approval_required: boolean;
  governance_requirements: string[];
  expires_at: string | null;
  recommendation_version: string;
  created_at: string;
  status: string;
}

export interface DecisionCandidate {
  decision_id: string;
  business_id: string;
  state_version: string;
  recommendation_id: string;
  action_type: string;
  deterministic_basis: Record<string, unknown>;
  advisory: AdvisoryResult | null;
  expected_impact: ImpactEstimate | null;
  risk: number;
  urgency: number;
  confidence: number;
  evidence_ids: string[];
  constraints: Record<string, unknown>;
  /** Set by Governance; Intelligence records it, never overrides it. */
  governance_status: string;
  approval_required: boolean;
  status: string;
  created_at: string;
  expires_at: string | null;
}

export interface Alert {
  alert_id: string;
  business_id: string;
  severity: string;
  alert_type: string;
  title: string;
  description: string;
  signal_id: string | null;
  recommendation_id: string | null;
  decision_id: string | null;
  evidence_ids: string[];
  created_at: string;
  expires_at: string | null;
  status: string;
  fingerprint: string;
}

export interface IntelligenceRun {
  run_id: string;
  business_id: string;
  state_version: string;
  started_at: string;
  completed_at: string | null;
  status: IntelligenceRunStatus;
  signals: Signal[];
  root_causes: RootCause[];
  impacts: ImpactEstimate[];
  recommendations: Recommendation[];
  decision_candidates: DecisionCandidate[];
  alerts: Alert[];
  evidence_ids: string[];
  /** Explicit limitations — e.g. insufficient data, partial run, stale input. */
  warnings: string[];
  failed_detectors: string[];
  detector_errors: Record<string, string>;
}

export interface CopilotAnswer {
  answer: string;
  sources: string[];
  evidence_ids: string[];
  related_signal_ids: string[];
  related_recommendation_ids: string[];
  confidence: number;
  freshness: FreshnessStatus;
  /** Present when the system cannot answer honestly. */
  limitations: string[];
  generated_at: string;
}

/* ── Paginated list envelopes ─────────────────────────────────────────────── */

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface RunRequest {
  business_id: string;
  state_version?: string | null;
  trigger?: string | null;
  /** Advisory is opt-in so a deterministic run never needs external AI. */
  enable_advisory?: boolean;
  shariah_approved?: boolean;
  detectors?: string[] | null;
}

/* ── Client ───────────────────────────────────────────────────────────────── */

const BASE = "/intelligence";

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.append(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}

export const intelligenceApi = {
  getContext(businessId: string, stateVersion?: string): Promise<BusinessContext> {
    return api
      .get<BusinessContext>(`${BASE}/context${qs({ business_id: businessId, state_version: stateVersion })}`)
      .then((r) => r.data);
  },

  getSignals(
    businessId: string,
    opts: { stateVersion?: string; domain?: string; severity?: string; limit?: number; offset?: number } = {},
  ): Promise<Page<Signal>> {
    return api
      .get<Page<Signal>>(
        `${BASE}/signals${qs({
          business_id: businessId,
          state_version: opts.stateVersion,
          domain: opts.domain,
          severity: opts.severity,
          limit: opts.limit,
          offset: opts.offset,
        })}`,
      )
      .then((r) => r.data);
  },

  getRootCauses(
    businessId: string,
    opts: { stateVersion?: string; causeType?: string; limit?: number; offset?: number } = {},
  ): Promise<Page<RootCause>> {
    return api
      .get<Page<RootCause>>(
        `${BASE}/root-causes${qs({
          business_id: businessId,
          state_version: opts.stateVersion,
          cause_type: opts.causeType,
          limit: opts.limit,
          offset: opts.offset,
        })}`,
      )
      .then((r) => r.data);
  },

  getImpacts(
    businessId: string,
    opts: { stateVersion?: string; kind?: ImpactKind; limit?: number; offset?: number } = {},
  ): Promise<Page<ImpactEstimate>> {
    return api
      .get<Page<ImpactEstimate>>(
        `${BASE}/impacts${qs({
          business_id: businessId,
          state_version: opts.stateVersion,
          kind: opts.kind,
          limit: opts.limit,
          offset: opts.offset,
        })}`,
      )
      .then((r) => r.data);
  },

  getRecommendations(
    businessId: string,
    opts: { stateVersion?: string; actionType?: string; limit?: number; offset?: number } = {},
  ): Promise<Page<Recommendation>> {
    return api
      .get<Page<Recommendation>>(
        `${BASE}/recommendations${qs({
          business_id: businessId,
          state_version: opts.stateVersion,
          action_type: opts.actionType,
          limit: opts.limit,
          offset: opts.offset,
        })}`,
      )
      .then((r) => r.data);
  },

  getDecisionCandidates(
    businessId: string,
    opts: { stateVersion?: string; limit?: number; offset?: number } = {},
  ): Promise<Page<DecisionCandidate>> {
    return api
      .get<Page<DecisionCandidate>>(
        `${BASE}/decisions${qs({
          business_id: businessId,
          state_version: opts.stateVersion,
          limit: opts.limit,
          offset: opts.offset,
        })}`,
      )
      .then((r) => r.data);
  },

  getAlerts(
    businessId: string,
    opts: { stateVersion?: string; severity?: string; limit?: number; offset?: number } = {},
  ): Promise<Page<Alert>> {
    return api
      .get<Page<Alert>>(
        `${BASE}/alerts${qs({
          business_id: businessId,
          state_version: opts.stateVersion,
          severity: opts.severity,
          limit: opts.limit,
          offset: opts.offset,
        })}`,
      )
      .then((r) => r.data);
  },

  monitor(request: RunRequest): Promise<IntelligenceRun> {
    return api.post<IntelligenceRun>(`${BASE}/monitor`, request).then((r) => r.data);
  },

  analyze(request: RunRequest): Promise<IntelligenceRun> {
    return api.post<IntelligenceRun>(`${BASE}/analyze`, request).then((r) => r.data);
  },

  copilot(request: {
    business_id: string;
    question: string;
    state_version?: string | null;
    enable_advisory?: boolean;
  }): Promise<CopilotAnswer> {
    return api.post<CopilotAnswer>(`${BASE}/copilot`, request).then((r) => r.data);
  },
};

/**
 * Render an impact with its kind always visible.
 *
 * Never present a potential/expected estimate as recovered money.
 */
export function formatImpact(impact: ImpactRef | ImpactEstimate | null | undefined): string {
  if (!impact) return "Not quantified";
  const label = impact.kind.toUpperCase();
  if (impact.kind === "verified") {
    return `${impact.amount_sar.toLocaleString("en-SA", {
      style: "currency",
      currency: "SAR",
      maximumFractionDigits: 0,
    })} (verified)`;
  }
  return `${impact.amount_sar.toLocaleString("en-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 0,
  })} (${label.toLowerCase()} only — not approved, executed or verified)`;
}

/** Human label for the data freshness of any Intelligence artifact. */
export function freshnessLabel(freshness: FreshnessStatus): string {
  switch (freshness) {
    case "fresh":
      return "Current";
    case "stale":
      return "Stale — revalidation required";
    case "partial":
      return "Partial data";
    case "missing":
      return "Missing data";
    case "conflict":
      return "Conflicting data";
    default:
      return "Unknown freshness";
  }
}
