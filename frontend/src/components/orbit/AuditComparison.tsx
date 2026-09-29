"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

interface DeltaValue {
  current: number;
  previous: number;
  delta: number;
  label: string;
  unit?: string;
  goodWhenPositive?: boolean; // true = green when positive, false = green when negative
}

interface AuditComparisonProps {
  comparison: {
    current: any;
    previous: any | null;
    delta: any;
  } | null;
  isLoading: boolean;
}

const formatCurrency = (value: number, currency = "SAR") => {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatNumber = (value: number) => {
  return new Intl.NumberFormat("en-US").format(value);
};

const getDeltaColor = (delta: number, goodWhenPositive = true) => {
  if (delta === 0) return "text-muted-foreground";
  const isGood = goodWhenPositive ? delta > 0 : delta < 0;
  return isGood ? "text-accent-green" : "text-accent-red";
};

const getDeltaBg = (delta: number, goodWhenPositive = true) => {
  const isGood = delta >= 0;
  return isGood ? "bg-accent-green/10 text-accent-green border-accent-green/30" : "bg-accent-red/10 text-accent-red border-accent-red/30";
};

export function AuditComparison({ comparison, isLoading }: AuditComparisonProps) {
  if (isLoading) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Audit Comparison
        </h3>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      </div>
    );
  }

  if (!comparison || !comparison.current) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1 text-center">
        <p className="text-muted-foreground">No comparison data available.</p>
      </div>
    );
  }

  const { current, previous, delta } = comparison;

  if (!previous) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Audit Comparison
        </h3>
        <div className="text-center py-8 text-brand-cream/60">
          <p className="text-brand-cream/60">No previous audit available for comparison.</p>
          <p className="text-sm text-brand-cream/40 mt-2">This is the first audit for this business.</p>
        </div>
      </div>
    );
  }

  const currentData = comparison.current;
  const previousData = comparison.previous;
  const deltaData = comparison.delta;

  const healthScoreDelta = deltaData?.health_score ?? 0;
  const capitalDelta = deltaData?.capital_exposed ?? 0;
  const revenueDelta = deltaData?.revenue_at_risk ?? 0;
  const profitDelta = deltaData?.profit_at_risk ?? 0;
  const recoverableLowDelta = deltaData?.recoverable_low ?? 0;
  const recoverableHighDelta = deltaData?.recoverable_high ?? 0;
  const findingsDelta = deltaData?.findings_count ?? 0;

  const formatDelta = (delta: number, prefix = "", isCurrency = false) => {
    const sign = delta > 0 ? "+" : "";
    const formatted = Math.abs(delta).toLocaleString();
    return `${prefix}${sign}${delta > 0 ? "+" : "-"}${formatNumber(Math.abs(delta))}`;
  };

  const formatCurrencyDelta = (delta: number) => {
    const sign = delta > 0 ? "+" : "";
    const formatted = Math.abs(delta).toLocaleString();
    return `${sign}${delta > 0 ? "+" : "-"}﷼ ${formatNumber(Math.abs(delta))}`;
  };

  return (
    <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Audit Comparison
        </h3>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="px-2 py-0.5 rounded-full bg-brand-cream/10 text-brand-cream/70">
            Current
          </span>
          <span className="text-brand-cream/40">vs</span>
          <span className="px-2 py-0.5 rounded-full bg-brand-cream/10 text-brand-cream/70">
            Previous
          </span>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
        <DeltaCard
          label="Health Score"
          current={currentData.health_score}
          previous={comparison.previous?.health_score ?? 0}
          delta={healthScoreDelta}
          goodWhenPositive={true}
        />
        <DeltaCard
          label="Capital Exposed"
          current={currentData.exposures?.capital_exposed_sar?.value ?? 0}
          previous={comparison.previous?.exposures?.capital_exposed_sar?.value ?? 0}
          delta={capitalDelta}
          isCurrency={true}
          goodWhenPositive={false}
        />
        <DeltaCard
          label="Revenue at Risk"
          current={currentData.exposures?.revenue_at_risk_sar?.value ?? 0}
          previous={comparison.previous?.exposures?.revenue_at_risk_sar?.value ?? 0}
          delta={revenueDelta}
          isCurrency={true}
          goodWhenPositive={false}
        />
        <DeltaCard
          label="Profit at Risk"
          current={currentData.exposures?.gross_profit_at_risk_sar?.value ?? 0}
          previous={comparison.previous?.exposures?.gross_profit_at_risk_sar?.value ?? 0}
          delta={profitDelta}
          isCurrency={true}
          goodWhenPositive={false}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-6">
        <DeltaCard
          label="Recoverable (Low)"
          current={currentData.exposures?.recoverable_range_sar?.low?.value ?? 0}
          previous={comparison.previous?.exposures?.recoverable_range_sar?.low?.value ?? 0}
          delta={comparison.delta?.recoverable_low ?? 0}
          isCurrency={true}
          goodWhenPositive={true}
        />
        <DeltaCard
          label="Recoverable (High)"
          current={currentData.exposures?.recoverable_range_sar?.high?.value ?? 0}
          previous={comparison.previous?.exposures?.recoverable_range_sar?.high?.value ?? 0}
          delta={comparison.delta?.recoverable_high ?? 0}
          isCurrency={true}
          goodWhenPositive={true}
        />
        <DeltaCard
          label="Total Findings"
          current={currentData.findings?.length ?? 0}
          previous={comparison.previous?.findings?.length ?? 0}
          delta={findingsDelta}
          goodWhenPositive={false}
        />
      </div>

      <div className="border-t border-brand-cream/10 pt-6">
        <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Findings by Category
        </h4>
        <div className="grid gap-2 md:grid-cols-3 lg:grid-cols-4">
          {Object.entries(comparison.delta?.findings_by_category ?? {}).map(([category, delta]: [string, any]) => (
            <div
              key={category}
              className={cn(
                "p-3 rounded-lg text-center",
                delta > 0
                  ? "bg-accent-red/10 border-accent-red/30"
                  : delta < 0
                  ? "bg-accent-green/10 border-accent-green/30"
                  : "bg-brand-cream/[0.03] border-brand-cream/5"
              )}
            >
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                {category}
              </p>
              <p className={cn("text-xl font-bold", delta > 0 ? "text-accent-red" : delta < 0 ? "text-accent-green" : "text-foreground")}>
                {delta > 0 ? "+" : ""}{delta}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface DeltaCardProps {
  label: string;
  current: number;
  previous: number;
  delta: number;
  isCurrency?: boolean;
  goodWhenPositive?: boolean;
}

function DeltaCard({ label, current, previous, delta, isCurrency, goodWhenPositive = true }: DeltaCardProps) {
  const formatValue = (val: number) => isCurrency
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "SAR", minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(val)
    : val.toLocaleString();

  const isGood = goodWhenPositive ? delta > 0 : delta < 0;
  const deltaColor = delta > 0 ? "text-accent-green" : delta < 0 ? "text-accent-red" : "text-muted-foreground";

  return (
    <div className="bg-surface rounded-lg border border-border p-4 shadow-elevation-1">
      <p className="text-xs text-muted-foreground uppercase tracking-wider mb-2">{label}</p>
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-bold text-foreground">{isCurrency ? `﷼ ${current.toLocaleString()}` : current.toLocaleString()}</span>
          <span className="text-sm text-muted-foreground">was {formatValue(previous)}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "px-2 py-0.5 rounded-full text-xs font-bold",
              delta > 0 ? "bg-accent-green/10 text-accent-green" : delta < 0 ? "bg-accent-red/10 text-accent-red" : "bg-muted/10 text-muted-foreground"
            )}
          >
            {delta > 0 ? "+" : ""}{delta.toLocaleString()}
          </span>
          <span className="text-xs text-muted-foreground">
            {delta > 0 ? "increase" : delta < 0 ? "decrease" : "no change"}
          </span>
        </div>
      </div>
    </div>
  );
}