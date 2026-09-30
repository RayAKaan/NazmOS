"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

interface MetricValue {
  value: number;
  currency: string;
  basis: string;
  period: string;
  confidence: string;
  evidence_ids: string[];
}

interface ExposureBreakdown {
  capital_exposed_sar: MetricValue;
  revenue_at_risk_sar: MetricValue;
  gross_profit_at_risk_sar: MetricValue;
  recoverable_range_sar: {
    low: MetricValue;
    high: MetricValue;
  };
}

interface ExposureCardsProps {
  exposures: ExposureBreakdown | null;
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

const getConfidenceColor = (confidence: string) => {
  switch (confidence?.toUpperCase()) {
    case "HIGH":
      return "text-accent-green border-accent-green/30";
    case "MEDIUM":
      return "text-accent-yellow border-accent-yellow/30";
    case "LOW":
      return "text-accent-red border-accent-red/30";
    default:
      return "text-muted-foreground border-border";
  }
};

const getConfidenceBg = (confidence: string) => {
  switch (confidence?.toUpperCase()) {
    case "HIGH":
      return "bg-accent-green/10 border-accent-green/30";
    case "MEDIUM":
      return "bg-accent-yellow/10 border-accent-yellow/30";
    case "LOW":
      return "bg-accent-red/10 border-accent-red/30";
    default:
      return "bg-muted/10 border-border";
  }
};

export function ExposureCards({ exposures, isLoading }: ExposureCardsProps) {
  if (isLoading || !exposures) {
    return (
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
            <Skeleton className="h-8 w-1/3 mb-2" />
            <Skeleton className="h-12 w-3/4 mb-2" />
            <Skeleton className="h-4 w-1/4" />
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      label: "Capital Currently Exposed",
      value: exposures.capital_exposed_sar,
      icon: "💰",
      color: "text-accent-red",
      bg: "bg-accent-red/10 border-accent-red/30",
    },
    {
      label: "Revenue Potentially at Risk",
      value: exposures.revenue_at_risk_sar,
      icon: "📉",
      color: "text-accent-yellow",
      bg: "bg-accent-yellow/10 border-accent-yellow/30",
    },
    {
      label: "Gross Profit Potentially Exposed",
      value: exposures.gross_profit_at_risk_sar,
      icon: "📊",
      color: "text-accent-yellow",
      bg: "bg-accent-yellow/10 border-accent-yellow/30",
    },
    {
      label: "Estimated Recoverable Range",
      value: {
        value: (exposures.recoverable_range_sar.low.value + exposures.recoverable_range_sar.high.value) / 2,
        currency: exposures.recoverable_range_sar.low.currency,
        confidence: exposures.recoverable_range_sar.low.confidence,
        basis: exposures.recoverable_range_sar.low.basis,
        period: exposures.recoverable_range_sar.low.period,
        evidence_ids: exposures.recoverable_range_sar.low.evidence_ids,
      },
      icon: "🔄",
      color: "text-accent-green",
      bg: "bg-accent-green/10 border-accent-green/30",
      isRange: true,
      low: exposures.recoverable_range_sar.low,
      high: exposures.recoverable_range_sar.high,
    },
  ];

  return (
    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, index) => (
        <div
          key={index}
          className={cn(
            "bg-surface rounded-lg border border-border p-6 shadow-elevation-1",
            card.bg
          )}
        >
          <div className="flex items-start justify-between mb-2">
            <span className="text-sm text-muted-foreground">{card.label}</span>
            <span className="text-2xl">{card.icon}</span>
          </div>
          {card.isRange ? (
            <>
              <div className="text-2xl font-bold text-foreground mb-1">
                {card.value.currency} {card.low.value.toLocaleString()} – {card.high.value.toLocaleString()}
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Recoverable Range</span>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded-full text-xs font-medium",
                    card.high.confidence === "HIGH"
                      ? "bg-accent-green/10 text-accent-green"
                      : card.high.confidence === "MEDIUM"
                      ? "bg-accent-yellow/10 text-accent-yellow"
                      : "bg-accent-red/10 text-accent-red"
                  )}
                >
                  {card.high.confidence} confidence
                </span>
              </div>
            </>
          ) : (
            <>
              <div className="text-3xl font-bold text-foreground mb-1">
                {card.value.currency} {card.value.value.toLocaleString()}
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{card.value.basis}</span>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded-full text-xs font-medium",
                    getConfidenceBg(card.value.confidence)
                  )}
                >
                  {card.value.confidence} confidence
                </span>
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
}