export interface GuestAuditSummary {
  money_at_risk_sar: number;
  inventory_value_sar: number;
  capital_at_risk_sar: number;
  revenue_at_risk_sar: number;
  gross_profit_at_risk_sar: number;
  recoverable_value_low_sar: number;
  recoverable_value_high_sar: number;
  expected_recovery_sar?: number | null;
  recovery_confidence: string;
  dead_stock_value_sar: number;
  stockout_risk_value_sar: number;
  margin_leakage_sar: number;
  overstock_value_sar: number;
  action_count: number;
  row_count: number;
  confidence_score: number;
  headline_note?: string;
  products_needing_attention?: number;
  guest_session_id: string;
  is_two_file?: boolean;
  is_arabic?: boolean;
  pairing?: {
    attempted: number;
    paired: number;
    high: number;
    medium: number;
    unmatched_sales: number;
    unmatched_inventory: number;
    success_rate: number;
    truncated: boolean;
  };
}

export interface GuestAuditAction {
  action_type: string;
  title: string;
  description: string;
  expected_recovery_sar?: number | null;
  recoverable_value_low_sar?: number | null;
  recoverable_value_high_sar?: number | null;
  recovery_confidence?: string;
  priority: number;
}

export interface GuestAuditResult {
  summary: GuestAuditSummary;
  actions: GuestAuditAction[];
  missing_data: { code: string; message: string }[];
}
