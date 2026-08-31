"use client";

import { useState } from "react";
import { Clock, TrendingDown, TrendingUp, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";

interface TimeMachineResult {
  horizon_days: number;
  do_nothing: {
    label: string;
    total_impact_sar: number;
    items_affected: number;
    estimated: boolean;
    item_details: { sku: string; product_name: string; financial_impact_sar: number; description: string }[];
  };
  nazmos_recommendation: {
    label: string;
    total_impact_sar: number;
    items_affected: number;
    estimated: boolean;
    item_details: { sku: string; product_name: string; financial_impact_sar: number; description: string }[];
  };
  estimated: boolean;
  label: string;
}

interface TimeMachineProps {
  auditId: string;
  businessId: string;
  className?: string;
}

function money(value: number | null | undefined) {
  if (value == null) return "—";
  const abs = Math.abs(Number(value));
  const formatted = `SAR ${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return value < 0 ? `-${formatted}` : formatted;
}

export function TimeMachine({ auditId, businessId, className }: TimeMachineProps) {
  const [horizon, setHorizon] = useState(30);
  const [result, setResult] = useState<TimeMachineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const simulate = async (days: number) => {
    setHorizon(days);
    setLoading(true);
    setError(null);
    try {
      const res = await api.post(`/money-audit/${auditId}/time-machine`, {
        business_id: businessId,
        horizon_days: days,
      });
      setResult(res.data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to simulate");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className={cn("rounded-3xl border border-border bg-surface p-6", className)}>
      <div className="flex items-center gap-2">
        <Clock className="h-5 w-5 text-brand-amber" />
        <h2 className="text-xl font-bold">What Happens If I Do Nothing?</h2>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Simulate the financial impact over time. Every result is a <span className="font-bold text-brand-amber">SIMULATION / ESTIMATE</span>.
      </p>

      {/* Horizon selector */}
      <div className="mt-4 flex gap-2">
        {[30, 60, 90].map((days) => (
          <button
            key={days}
            onClick={() => simulate(days)}
            disabled={loading}
            className={cn(
              "rounded-xl px-4 py-2 text-sm font-bold transition-all",
              horizon === days
                ? "bg-brand-amber text-brand-night"
                : "border border-border bg-brand-night/5 text-muted-foreground hover:bg-brand-night/10"
            )}
          >
            {days} days
          </button>
        ))}
      </div>

      {loading && (
        <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-amber border-t-transparent" />
          Simulating...
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-xl bg-brand-red/10 p-3 text-sm text-brand-red">
          {error}
        </div>
      )}

      {result && !loading && (
        <div className="mt-6 space-y-4">
          {/* Comparison summary */}
          <div className="grid gap-4 sm:grid-cols-2">
            <ScenarioCard
              label={result.do_nothing.label}
              impact={result.do_nothing.total_impact_sar}
              itemsAffected={result.do_nothing.items_affected}
              icon={<TrendingDown className="h-5 w-5" />}
              variant="destructive"
            />
            <ScenarioCard
              label={result.nazmos_recommendation.label}
              impact={result.nazmos_recommendation.total_impact_sar}
              itemsAffected={result.nazmos_recommendation.items_affected}
              icon={<TrendingUp className="h-5 w-5" />}
              variant="success"
            />
          </div>

          {/* Impact label */}
          <div className="flex items-center gap-2 rounded-xl bg-brand-amber/10 p-3 text-sm text-brand-amber">
            <AlertTriangle className="h-4 w-4" />
            <span className="font-bold">SIMULATION / ESTIMATE</span> — This is not actual recovery. Actual outcomes depend on execution and market conditions.
          </div>

          {/* Net difference */}
          <div className="rounded-2xl bg-brand-night/5 p-4">
            <div className="text-sm text-muted-foreground">
              Net impact of following NazmOS recommendation vs doing nothing:
            </div>
            <div className={cn(
              "mt-1 text-2xl font-bold",
              result.nazmos_recommendation.total_impact_sar > result.do_nothing.total_impact_sar
                ? "text-brand-green"
                : "text-brand-red"
            )}>
              {money(result.nazmos_recommendation.total_impact_sar - result.do_nothing.total_impact_sar)}
            </div>
          </div>

          {/* Item details */}
          <details className="rounded-2xl border border-border bg-brand-night/5">
            <summary className="cursor-pointer p-4 text-sm font-bold text-muted-foreground hover:text-foreground">
              Show per-item breakdown ({result.do_nothing.item_details.length} items)
            </summary>
            <div className="border-t border-border p-4">
              <div className="grid gap-2 text-xs">
                <div className="grid grid-cols-4 gap-2 font-bold text-muted-foreground">
                  <div>Product</div>
                  <div className="text-right">Do Nothing</div>
                  <div className="text-right">NazmOS</div>
                  <div>Notes</div>
                </div>
                {result.do_nothing.item_details.map((item, idx) => {
                  const nzItem = result.nazmos_recommendation.item_details[idx];
                  return (
                    <div key={idx} className="grid grid-cols-4 gap-2 border-t border-border/50 pt-2">
                      <div className="truncate text-foreground">{item.product_name || item.sku}</div>
                      <div className={cn("text-right font-mono", item.financial_impact_sar < 0 ? "text-brand-red" : "text-muted-foreground")}>
                        {money(item.financial_impact_sar)}
                      </div>
                      <div className={cn("text-right font-mono", nzItem?.financial_impact_sar > 0 ? "text-brand-green" : "text-muted-foreground")}>
                        {nzItem ? money(nzItem.financial_impact_sar) : "—"}
                      </div>
                      <div className="truncate text-muted-foreground">{item.description}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </details>
        </div>
      )}

      {!result && !loading && (
        <div className="mt-6 rounded-2xl bg-brand-night/5 p-8 text-center text-sm text-muted-foreground">
          Select a time horizon to simulate the impact of doing nothing vs following NazmOS recommendations.
        </div>
      )}
    </section>
  );
}

function ScenarioCard({
  label,
  impact,
  itemsAffected,
  icon,
  variant,
}: {
  label: string;
  impact: number;
  itemsAffected: number;
  icon: React.ReactNode;
  variant: "destructive" | "success";
}) {
  return (
    <div className={cn(
      "rounded-2xl border p-4",
      variant === "destructive" ? "border-brand-red/25 bg-brand-red/5" : "border-brand-green/25 bg-brand-green/5"
    )}>
      <div className="flex items-center gap-2">
        <div className={cn(
          "flex h-8 w-8 items-center justify-center rounded-full",
          variant === "destructive" ? "bg-brand-red/20 text-brand-red" : "bg-brand-green/20 text-brand-green"
        )}>
          {icon}
        </div>
        <div>
          <div className="text-sm font-bold text-foreground">{label}</div>
          <div className="text-xs text-muted-foreground">{itemsAffected} items affected</div>
        </div>
      </div>
      <div className={cn(
        "mt-3 text-2xl font-bold",
        variant === "destructive" ? "text-brand-red" : "text-brand-green"
      )}>
        {money(impact)}
      </div>
      <div className="text-xs text-muted-foreground">estimated net impact</div>
    </div>
  );
}
