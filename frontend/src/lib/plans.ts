export type PlanKey = "free" | "basic" | "pro" | "enterprise";

export const PLAN_LABELS: Record<PlanKey, string> = {
  free: "Free Money Audit",
  basic: "Small Retail",
  pro: "Growing Retail",
  enterprise: "Large Chains",
};

export const FEATURE_LABELS: Record<string, string> = {
  forecasting: "Forecasting",
  pricing_optimization: "Price Shield",
  multi_branch_rebalancing: "Branch Rebalancing",
  dead_stock_detection: "Dead Stock Detection",
  stockout_risk: "Stockout Risk",
  margin_leakage: "Margin Leakage",
  weekly_money_report: "Weekly Money Report",
  live_whatsapp: "Live WhatsApp Approvals",
  mock_whatsapp: "Mock WhatsApp Approvals",
  recovery_match_preview: "Recovery Match Preview",
  recovery_match: "Recovery Match",
  recovery_match_contact_reveal: "Recovery Match Contact Reveal",
  supplier_directory: "Supplier Directory",
  supplier_marketplace: "Supplier Marketplace",
  api_access: "API Access",
  custom_reports: "Custom Reports",
};

export function lockedMessage(feature: string) {
  return `${FEATURE_LABELS[feature] || feature} is available after the Free Money Audit.`;
}
