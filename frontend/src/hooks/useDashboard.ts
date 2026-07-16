import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import {
  DashboardSummary,
  AlertsResponse,
  SalesTrend,
  TopProductsResponse,
  DeadStockResponse,
  HourlyPattern,
  CategoryBreakdown,
} from "@/types/dashboard";

export function useDashboard() {
  const { businessId } = useAppStore();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null);
  const [salesTrend, setSalesTrend] = useState<SalesTrend | null>(null);
  const [topProducts, setTopProducts] = useState<TopProductsResponse | null>(null);
  const [deadStock, setDeadStock] = useState<DeadStockResponse | null>(null);
  const [hourlyPattern, setHourlyPattern] = useState<HourlyPattern | null>(null);
  const [categoryBreakdown, setCategoryBreakdown] = useState<CategoryBreakdown | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!businessId) return;
    
    setIsLoading(true);
    setError(null);

    try {
      const [summaryRes, alertsRes, salesRes, productsRes, deadRes, hourlyRes, categoryRes] = await Promise.all([
        api.get(`/dashboard/summary?business_id=${businessId}`),
        api.get(`/dashboard/alerts?business_id=${businessId}`),
        api.get(`/dashboard/sales-trend?business_id=${businessId}&period=30`),
        api.get(`/dashboard/top-products?business_id=${businessId}&period=7&limit=5`),
        api.get(`/dashboard/dead-stock?business_id=${businessId}`),
        api.get(`/dashboard/hourly-pattern?business_id=${businessId}&period=30`),
        api.get(`/dashboard/category-breakdown?business_id=${businessId}&period=30`),
      ]);

      setSummary(summaryRes.data);
      setAlerts(alertsRes.data);
      setSalesTrend(salesRes.data);
      setTopProducts(productsRes.data);
      setDeadStock(deadRes.data);
      setHourlyPattern(hourlyRes.data);
      setCategoryBreakdown(categoryRes.data);
    } catch (err) {
      setError("Failed to load dashboard data");
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    summary,
    alerts,
    salesTrend,
    topProducts,
    deadStock,
    hourlyPattern,
    categoryBreakdown,
    isLoading,
    error,
    refetch: fetchData,
  };
}
