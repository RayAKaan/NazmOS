export interface IntelligenceDecisionAction {
  action_type?: string;
  title?: string;
  description?: string;
  expected_value_sar?: number;
  confidence?: number;
}

export interface IntelligenceDecision {
  id?: string;
  ranked_action?: IntelligenceDecisionAction | null;
  candidate_actions?: IntelligenceDecisionAction[];
  composite_score?: number;
  status?: string;
  created_at?: string;
}

export interface IntelligenceSummary {
  summary: string;
  recent_event_count: number;
  top_action: IntelligenceDecisionAction | null;
  sources: string[];
}

export interface IntelligenceReasonRequest {
  question: string;
  context?: Record<string, unknown>;
}

export interface IntelligenceReasonResponse {
  answer: string;
  decision: IntelligenceDecisionAction | null;
  plan: { goal: string; steps: string[] } | null;
  sources: string[];
}

export interface IntelligenceAnalyzeRequest {
  query?: string;
  decision_type?: string;
  context?: Record<string, unknown>;
}

export interface IntelligenceAnalyzeResponse {
  query: string | null;
  summary: string;
  memory_snapshot: Record<string, unknown>;
  graph_evidence: Record<string, unknown>[];
  context_evidence: Record<string, unknown>;
  recent_event_count: number;
  decision: IntelligenceDecision | null;
  sources: string[];
}

export interface IntelligencePredictRequest {
  target: "sales" | "demand" | "stock";
  horizon_days?: number;
  item_id?: string;
}

export interface IntelligencePredictResponse {
  target: string;
  horizon_days: number;
  item_id: string | null;
  predicted_value: number;
  unit: string;
  confidence: number;
  basis: string[];
}

export interface ChatSuggestion {
  suggestions: string[];
  context_summary: string;
}
