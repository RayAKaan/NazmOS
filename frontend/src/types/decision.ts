export type DecisionType = "restock" | "discount" | "promotion" | "alert" | "forecast" | "general";
export type DecisionPriority = "high" | "medium" | "low";
export type DecisionStatus = "pending" | "accepted" | "dismissed" | "completed" | "expired";

export interface Decision {
  id: string;
  type: DecisionType;
  title: string;
  description: string;
  priority: DecisionPriority;
  confidence: number;
  reasoning?: string;
  items: DecisionItem[];
  status: DecisionStatus;
  business_id: string;
  created_at: string;
  expires_at?: string;
  implemented_at?: string;
  user_id?: string;
  metadata?: Record<string, unknown>;
}

export interface DecisionItem {
  id?: string;
  product_name?: string;
  product_id?: string;
  sku?: string;
  current_stock?: number;
  suggested_action?: string;
  quantity?: number;
  reason?: string;
  priority?: DecisionPriority;
  expected_impact?: {
    revenue?: number;
    savings?: number;
    units_sold?: number;
  };
}

export interface DecisionRequest {
  business_id: string;
  query: string;
  context?: {
    include_inventory?: boolean;
    include_sales?: boolean;
    include_forecasts?: boolean;
    time_range?: "7d" | "30d" | "90d";
  };
}

export interface DecisionResponse {
  decisions: Decision[];
  session_id?: string;
  message?: string;
  generated_at: string;
  processing_time_ms: number;
}

export interface DecisionHistory {
  decisions: Decision[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    total_pages: number;
  };
}

export interface DecisionStats {
  total_decisions: number;
  by_priority: Record<DecisionPriority, number>;
  by_type: Record<DecisionType, number>;
  by_status: Record<DecisionStatus, number>;
  avg_confidence: number;
  implemented_count: number;
  potential_impact: {
    revenue_opportunity: number;
    cost_savings: number;
  };
}

export const PRIORITY_COLORS: Record<DecisionPriority, string> = {
  high: "text-red-400 bg-red-500/10",
  medium: "text-yellow-400 bg-yellow-500/10",
  low: "text-blue-400 bg-blue-500/10",
};

export const PRIORITY_ICONS: Record<DecisionPriority, string> = {
  high: "🔴",
  medium: "🟡",
  low: "🔵",
};

export const TYPE_LABELS: Record<DecisionType, string> = {
  restock: "Restock Required",
  discount: "Discount Opportunity",
  promotion: "Promotion Idea",
  alert: "Alert",
  forecast: "Forecast Insight",
  general: "General Insight",
};

export const TYPE_COLORS: Record<DecisionType, string> = {
  restock: "text-orange-400 bg-orange-500/10",
  discount: "text-green-400 bg-green-500/10",
  promotion: "text-purple-400 bg-purple-500/10",
  alert: "text-red-400 bg-red-500/10",
  forecast: "text-blue-400 bg-blue-500/10",
  general: "text-gray-400 bg-gray-500/10",
};
