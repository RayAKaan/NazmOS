export interface InventoryItem {
  item_id: string;
  name: string;
  sku: string | null;
  category: string | null;
  current_stock: number;
  unit: string;
  daily_avg_sale: number;
  days_until_stockout: number | null;
  cost_price: number;
  sell_price: number;
  stock_value: number;
  status: "critical" | "low" | "healthy" | "overstock" | "dead";
  last_restocked: string | null;
  reorder_level: number;
  trend_7d: "up" | "down" | "stable";
}

export interface InventorySummary {
  total_items: number;
  total_stock_value: number;
  critical_count: number;
  low_count: number;
  healthy_count: number;
  overstock_count: number;
  dead_count: number;
}

export interface InventoryResponse {
  items: InventoryItem[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    total_pages: number;
  };
  summary: InventorySummary;
}

export interface SalesHistoryItem {
  date: string;
  quantity: number;
}

export interface ForecastItem {
  date: string;
  predicted_qty: number;
}

export interface ReorderRecommendation {
  should_reorder: boolean;
  recommended_qty: number;
  recommended_by_date: string | null;
  reason: string | null;
}

export interface ItemDetail {
  item: InventoryItem;
  sales_history_30d: SalesHistoryItem[];
  forecast_7d: ForecastItem[];
  reorder_recommendation: ReorderRecommendation;
}
