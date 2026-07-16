export interface TodaySummary {
  sales: number;
  transactions: number;
  profit: number;
  avg_basket_size: number;
}

export interface MonthSummary {
  sales: number;
  transactions: number;
  profit: number;
}

export interface ComparisonData {
  sales_change_percent: number;
  profit_change_percent: number;
  vs_last_month: boolean;
}

export interface DashboardSummary {
  today: TodaySummary;
  this_month: MonthSummary;
  comparison: ComparisonData;
  health_score: number;
}

export interface Alert {
  id: string;
  type: "critical" | "warning" | "info" | "success";
  icon: string;
  title: string;
  message: string;
  detail: string | null;
  action_text: string | null;
  action_type: string | null;
  item_id: string | null;
  priority: number;
  created_at: string;
}

export interface AlertsResponse {
  alerts: Alert[];
}

export interface SalesTrendItem {
  date: string;
  sales: number;
  profit: number;
  transactions: number;
}

export interface SalesTrendSummary {
  avg_daily_sales: number;
  best_day: string;
  worst_day: string;
  trend_direction: "up" | "down" | "stable";
}

export interface SalesTrend {
  data: SalesTrendItem[];
  summary: SalesTrendSummary;
}

export interface TopProduct {
  item_id: string;
  name: string;
  category: string;
  total_qty: number;
  total_revenue: number;
  total_profit: number;
  avg_daily_qty: number;
  trend: "up" | "down" | "stable";
  rank: number;
}

export interface TopProductsResponse {
  products: TopProduct[];
}

export interface DeadStockItem {
  item_id: string;
  name: string;
  category: string;
  current_stock: number;
  stock_value: number;
  last_sold_at: string | null;
  days_since_last_sale: number | null;
  recommendation: "discount" | "remove" | "bundle";
}

export interface DeadStockResponse {
  items: DeadStockItem[];
  total_stuck_value: number;
}

export interface HourlyPatternItem {
  hour: number;
  avg_sales: number;
  avg_transactions: number;
  label: string;
}

export interface HourlyPattern {
  pattern: HourlyPatternItem[];
  peak_hours: number[];
  slow_hours: number[];
}

export interface CategoryBreakdownItem {
  name: string;
  total_sales: number;
  percentage: number;
  item_count: number;
  top_item: string | null;
}

export interface CategoryBreakdown {
  categories: CategoryBreakdownItem[];
}
