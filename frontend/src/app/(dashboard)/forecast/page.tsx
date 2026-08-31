"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarRange, RefreshCw, Sparkles, TrendingDown, TrendingUp, MoveRight } from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { LoadingState } from "@/components/ui/LoadingState";
import { EmptyState } from "@/components/ui/EmptyState";
import { cn } from "@/lib/utils";

interface CachedForecast {
  item_id: string;
  item_name: string | null;
  model_version: string | null;
  trend_direction: "up" | "down" | "stable" | null;
  trend_strength: number;
  trained_at: string | null;
  expires_at: string | null;
}

interface SummaryResponse {
  total_forecasts: number;
  trending_up: number;
  trending_down: number;
  stable: number;
  avg_trend_strength: number;
  last_trained_at: string | null;
}

function trendTone(trend: string | null) {
  if (trend === "up") return "text-brand-green bg-brand-green/10 border-brand-green/25";
  if (trend === "down") return "text-brand-red-light bg-brand-red/10 border-brand-red/25";
  return "text-muted-foreground bg-brand-cream/5 border-brand-cream/10";
}

function trendLabel(trend: string | null) {
  if (trend === "up") return "Trending up";
  if (trend === "down") return "Trending down";
  return "Stable";
}

export default function ForecastPage() {
  const { businessId } = useAppStore();
  const [forecasts, setForecasts] = useState<CachedForecast[] | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [selected, setSelected] = useState<CachedForecast | null>(null);
  const [detail, setDetail] = useState<{ forecast_7d?: Array<{ date: string; predicted_qty: number }>; from_cache?: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setError(null);
    try {
      const [cacheRes, summaryRes] = await Promise.all([
        api.get(`/forecast/cache?business_id=${businessId}&limit=200`),
        api.get(`/forecast/summary?business_id=${businessId}`),
      ]);
      setForecasts(cacheRes.data.forecasts);
      setSummary(summaryRes.data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not load demand forecasts. Upload sales and inventory files first.");
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (forecast: CachedForecast) => {
    setSelected(forecast);
    setDetail(null);
    try {
      const res = await api.get(`/forecast/${forecast.item_id}?business_id=${businessId}`);
      setDetail(res.data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setDetail({ from_cache: false });
      setError(typeof detail === "string" ? detail : "Could not load this forecast.");
    }
  };

  const generate = async () => {
    if (!businessId) return;
    setWorking(true);
    setError(null);
    try {
      const res = await api.get(`/forecast/cache?business_id=${businessId}&limit=200`);
      const list: CachedForecast[] = res.data.forecasts;
      const itemId = list.length > 0 ? list[0].item_id : undefined;
      await api.post(`/forecast/?business_id=${businessId}${itemId ? `&item_id=${itemId}` : ""}`);
      await load();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not generate forecast yet. Import data and try again.");
    } finally {
      setWorking(false);
    }
  };

  if (loading) return <LoadingState label="Loading demand forecasts…" variant="cards" />;

  const noData = !forecasts || forecasts.length === 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Demand Forecast</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            AI demand predictions per item — KSA edition, Prophet-powered.
          </p>
        </div>
        <button
          onClick={generate}
          disabled={working || noData}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-amber px-4 py-2.5 text-sm font-bold text-brand-night hover:bg-brand-gold disabled:cursor-not-allowed disabled:opacity-50"
        >
          {working ? <RefreshCw className="h-4 w-4 animate-spin" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
          Refresh forecasts
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-brand-red/25 bg-brand-red/10 px-4 py-3 text-sm text-brand-red-light">
          {error}
        </div>
      )}

      {noData && !error ? (
        <EmptyState
          icon={CalendarRange}
          title="No forecasts yet"
          description="Upload sales and inventory files to start generating AI demand forecasts for every item."
          actions={[{ label: "Upload files", href: "/upload", primary: true }, { label: "View sample audit", href: "/product-demo" }]}
        />
      ) : (
        <>
          {summary && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Active forecasts", value: summary.total_forecasts },
                { label: "Trending up", value: summary.trending_up },
                { label: "Trending down", value: summary.trending_down },
                { label: "Stable", value: summary.stable },
              ].map((stat) => (
                <div key={stat.label} className="rounded-2xl border border-border bg-card p-4">
                  <p className="text-sm text-muted-foreground">{stat.label}</p>
                  <p className="mt-2 text-2xl font-bold text-foreground">{stat.value}</p>
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="border-b border-border p-4">
                <h2 className="text-lg font-semibold text-foreground">Forecasted items</h2>
              </div>
              <div className="divide-y divide-border">
                {forecasts!.map((forecast) => (
                  <button
                    key={forecast.item_id}
                    onClick={() => openDetail(forecast)}
                    className={cn(
                      "flex w-full items-center justify-between gap-4 p-4 text-left transition-colors hover:bg-muted",
                      selected?.item_id === forecast.item_id && "bg-muted"
                    )}
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium text-foreground">{forecast.item_name || "Unnamed item"}</p>
                      <p className="text-sm text-muted-foreground">
                        {forecast.trained_at ? new Date(forecast.trained_at).toLocaleDateString() : "Not trained"}
                      </p>
                    </div>
                    <span className={cn("rounded-full border px-3 py-1 text-xs font-semibold", trendTone(forecast.trend_direction))}>
                      {trendLabel(forecast.trend_direction)}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-card p-5">
              {!selected ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <TrendingUp className="h-10 w-10 text-muted-foreground" aria-hidden />
                  <p className="mt-4 font-medium text-foreground">Select an item</p>
                  <p className="mt-1 text-sm text-muted-foreground">Pick a forecasted item to view its demand curve.</p>
                </div>
              ) : !detail ? (
                <LoadingState label="Loading forecast detail…" variant="chart" />
              ) : (
                <div>
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className={cn("flex h-11 w-11 items-center justify-center rounded-xl", selected.trend_direction === "down" ? "bg-brand-red/10 text-brand-red-light" : "bg-brand-green/10 text-brand-green")}>
                        {selected.trend_direction === "down" ? <TrendingDown className="h-5 w-5" aria-hidden /> : <TrendingUp className="h-5 w-5" aria-hidden />}
                      </div>
                      <div>
                        <h3 className="font-semibold text-foreground">{selected.item_name || "Unnamed item"}</h3>
                        <p className="text-sm text-muted-foreground">{selected.model_version || "model"} · {selected.trend_strength.toFixed(2)} strength</p>
                      </div>
                    </div>
                    {detail.from_cache !== undefined && (
                      <span className="rounded-full border border-brand-cream/10 bg-brand-cream/5 px-3 py-1 text-xs font-semibold text-muted-foreground">
                        {detail.from_cache ? "Cached" : "Fallback"}
                      </span>
                    )}
                  </div>

                  {detail.forecast_7d && detail.forecast_7d.length > 0 ? (
                    <div className="mt-6 space-y-2">
                      <div className="flex items-end gap-1.5 h-40">
                        {detail.forecast_7d.map((day, i) => {
                          const max = Math.max(...detail.forecast_7d!.map((d) => d.predicted_qty), 1);
                          const height = Math.max((day.predicted_qty / max) * 100, 4);
                          return (
                            <div key={i} className="flex-1 flex flex-col items-center gap-1">
                              <span className="text-[10px] text-muted-foreground">{Math.round(day.predicted_qty)}</span>
                              <div
                                className={cn("w-full rounded-t-md", day.predicted_qty > 0 ? "bg-brand-amber" : "bg-muted")}
                                style={{ height: `${height}%` }}
                              />
                              <span className="text-[10px] text-muted-foreground">
                                {new Date(day.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "narrow" })}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                      <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                        <MoveRight className="h-4 w-4" aria-hidden /> 7-day demand projection per item
                      </p>
                    </div>
                  ) : (
                    <p className="mt-6 rounded-xl border border-brand-cream/10 bg-brand-cream/5 p-4 text-sm text-muted-foreground">
                      No forecast curve available yet. Refresh forecasts after importing enough sales history.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
