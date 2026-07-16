export interface ForecastPeriod {
  date: string;
  predicted: number;
  lower_bound: number;
  upper_bound: number;
  trend: "up" | "down" | "stable";
  confidence: number;
}

export interface ProductForecast {
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  periods: ForecastPeriod[];
  model: string;
  mape: number;
  seasonality: {
    weekly: number;
    yearly: number;
  };
  trend: "increasing" | "decreasing" | "stable";
  generated_at: string;
  cache_key: string;
}

export interface CategoryForecast {
  category: string;
  total_predicted: number;
  period_over_period_change: number;
  percentage_change: number;
  confidence: number;
  products: Array<{
    product_id: string;
    product_name: string;
    predicted: number;
    contribution: number;
  }>;
}

export interface ForecastRequest {
  business_id: string;
  days: number;
  product_ids?: string[];
  categories?: string[];
  granularity?: "daily" | "weekly" | "monthly";
}

export interface ForecastResponse {
  forecasts: ProductForecast[];
  category_forecasts: CategoryForecast[];
  summary: ForecastSummary;
  generated_at: string;
  cached: boolean;
  cache_expires_at?: string;
}

export interface ForecastSummary {
  total_products_forecasted: number;
  overall_trend: "increasing" | "decreasing" | "stable";
  predicted_total_sales: number;
  predicted_revenue: number;
  high_demand_products: Array<{
    product_id: string;
    product_name: string;
    predicted_demand: number;
    current_stock: number;
    restock_needed: boolean;
  }>;
  low_demand_products: Array<{
    product_id: string;
    product_name: string;
    predicted_demand: number;
    current_stock: number;
    days_until_stockout: number;
  }>;
  seasonal_opportunities: SeasonalOpportunity[];
}

export interface SeasonalOpportunity {
  festival_name?: string;
  event_name?: string;
  date: string;
  expected_boost_percent: number;
  relevant_categories: string[];
  products: Array<{
    product_name: string;
    predicted_increase: number;
  }>;
}

export interface ForecastComparison {
  product_id: string;
  product_name: string;
  period: string;
  actual?: number;
  predicted?: number;
  error_percent: number;
  within_confidence: boolean;
}

export interface ForecastAlert {
  id: string;
  type: "stockout" | "overstock" | "demand_surge" | "demand_drop";
  product_id: string;
  product_name: string;
  severity: "critical" | "warning" | "info";
  message: string;
  suggested_action: string;
  created_at: string;
}

export interface ForecastCache {
  cache_key: string;
  business_id: string;
  forecast_type: "product" | "category" | "summary";
  parameters: Record<string, unknown>;
  expires_at: string;
  created_at: string;
}
