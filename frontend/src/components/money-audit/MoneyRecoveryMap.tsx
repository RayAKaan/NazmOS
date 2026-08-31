"use client";

import { cn } from "@/lib/utils";

interface MoneyRecoveryMapProps {
  inventoryValue: number;
  deadStockValue: number;
  overstockValue: number;
  stockoutRiskValue: number;
  marginLeakage: number;
  capitalAtRisk: number;
  recoverableLow: number;
  recoverableHigh: number;
  className?: string;
}

function money(value: number) {
  return `SAR ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function pct(value: number, total: number) {
  if (total <= 0) return "0%";
  return `${Math.round((value / total) * 100)}%`;
}

function BarSegment({ value, total, color, label }: { value: number; total: number; color: string; label: string }) {
  if (value <= 0 || total <= 0) return null;
  const width = Math.max((value / total) * 100, 2);
  return (
    <div className="group relative" style={{ width: `${width}%` }}>
      <div className={cn("h-3 rounded-full transition-all duration-300", color)} />
      <div className="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-brand-night px-2 py-1 text-xs text-brand-cream opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
        {label}: {money(value)}
      </div>
    </div>
  );
}

export function MoneyRecoveryMap({
  inventoryValue,
  deadStockValue,
  overstockValue,
  stockoutRiskValue,
  marginLeakage,
  capitalAtRisk,
  recoverableLow,
  recoverableHigh,
  className,
}: MoneyRecoveryMapProps) {
  const healthyValue = Math.max(0, inventoryValue - deadStockValue - overstockValue);
  const total = inventoryValue || 1;

  return (
    <section className={cn("rounded-3xl border border-border bg-surface p-6", className)}>
      <div className="mb-4">
        <h2 className="text-2xl font-bold">I Found Where Your Money Is Trapped</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Breakdown of your {money(inventoryValue)} inventory value by financial status.
        </p>
      </div>

      {/* Visual Bar */}
      <div className="flex gap-1 overflow-hidden rounded-full">
        <BarSegment value={healthyValue} total={total} color="bg-brand-green" label="Healthy" />
        <BarSegment value={deadStockValue} total={total} color="bg-brand-red" label="Dead Stock" />
        <BarSegment value={overstockValue} total={total} color="bg-brand-amber" label="Overstock" />
        <BarSegment value={stockoutRiskValue} total={total} color="bg-yellow-500" label="Stockout Risk" />
        <BarSegment value={marginLeakage} total={total} color="bg-orange-400" label="Margin Leakage" />
      </div>

      {/* Legend */}
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <LegendItem
          color="bg-brand-green"
          label="Healthy"
          amount={healthyValue}
          pct={pct(healthyValue, total)}
          description="Moving at expected velocity"
        />
        <LegendItem
          color="bg-brand-red"
          label="Trapped — Dead Stock"
          amount={deadStockValue}
          pct={pct(deadStockValue, total)}
          description="No recent sales, capital locked"
        />
        <LegendItem
          color="bg-brand-amber"
          label="Trapped — Overstock"
          amount={overstockValue}
          pct={pct(overstockValue, total)}
          description="Excess beyond 30-day demand"
        />
        <LegendItem
          color="bg-yellow-500"
          label="At Risk — Stockout"
          amount={stockoutRiskValue}
          pct={pct(stockoutRiskValue, total)}
          description="Revenue at risk from projected stockout"
        />
        <LegendItem
          color="bg-orange-400"
          label="At Risk — Margin Leakage"
          amount={marginLeakage}
          pct={pct(marginLeakage, total)}
          description="Profit opportunity below target margin"
        />
        <LegendItem
          color="bg-brand-green/30 border border-brand-green/50"
          label="Potentially Recoverable"
          amount={recoverableHigh}
          pct=""
          description={`Range: ${money(recoverableLow)}–${money(recoverableHigh)}`}
        />
      </div>
    </section>
  );
}

function LegendItem({
  color,
  label,
  amount,
  pct: pctValue,
  description,
}: {
  color: string;
  label: string;
  amount: number;
  pct: string;
  description: string;
}) {
  if (amount <= 0 && label !== "Healthy") return null;
  return (
    <div className="flex items-start gap-3 rounded-2xl bg-brand-night/5 p-3">
      <div className={cn("mt-0.5 h-3 w-3 shrink-0 rounded-full", color)} />
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-bold text-foreground">{label}</span>
          {pctValue && <span className="text-xs text-muted-foreground">{pctValue}</span>}
        </div>
        <div className="text-lg font-bold text-foreground">{money(amount)}</div>
        <div className="text-xs text-muted-foreground">{description}</div>
      </div>
    </div>
  );
}
