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

interface OpportunityCard {
  rank: number;
  title: string;
  exposure_sar: {
    value: number;
    currency: string;
    basis: string;
    period: string;
    confidence: string;
    evidence_ids: string[];
  };
  unit_count: number;
  recoverable_range_sar: {
    low: { value: number; currency: string; confidence: string };
    high: { value: number; currency: string; confidence: string };
  };
  confidence: string;
}

interface TopOpportunitiesProps {
  opportunities: any[];
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
      return "text-accent-green";
    case "MEDIUM":
      return "text-accent-yellow";
    case "LOW":
      return "text-accent-red";
    default:
      return "text-muted-foreground";
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

export function TopOpportunities({ opportunities, isLoading }: TopOpportunitiesProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-surface rounded-lg border border-border p-5 shadow-elevation-1">
            <Skeleton className="h-6 w-1/2 mb-2" />
            <Skeleton className="h-4 w-3/4 mb-2" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  if (!opportunities || opportunities.length === 0) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1 text-center">
        <p className="text-muted-foreground">No priority opportunities found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
        Top 3 Opportunities
      </h3>
      <div className="space-y-3">
        {opportunities.slice(0, 3).map((opp, index) => (
          <div
            key={opp.title || index}
            className="bg-surface rounded-lg border border-border p-5 shadow-elevation-1 hover:shadow-elevation-2 transition-shadow"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={cn(
                      "px-2 py-0.5 rounded-full text-xs font-bold",
                      "bg-brand-amber/20 text-brand-amber"
                    )}
                  >
                    #{index + 1}
                  </span>
                  <h4 className="font-semibold text-lg text-foreground truncate">
                    {opp.title}
                  </h4>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={cn(
                      "px-2 py-1 rounded-full text-xs font-bold",
                      opp.confidence === "HIGH"
                        ? "bg-accent-green/10 text-accent-green border-accent-green/30"
                        : opp.confidence === "MEDIUM"
                        ? "bg-accent-yellow/10 text-accent-yellow border-accent-yellow/30"
                        : "bg-accent-red/10 text-accent-red border-accent-red/30"
                    )}
                  >
                    {opp.confidence}
                  </span>
                </div>
              </div>

              <div className="grid md:grid-cols-3 gap-4 mt-4">
                <div className="rounded-lg bg-brand-cream/[0.03] p-3 border border-brand-cream/5">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                    Capital Exposed
                  </p>
                  <p className="font-bold text-lg text-foreground">
                    {opp.exposure_sar?.currency} {opp.exposure_sar?.value?.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-lg bg-brand-cream/[0.03] p-3 border border-brand-cream/5">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                    Units Affected
                  </p>
                  <p className="font-bold text-lg text-foreground">{opp.unit_count?.toLocaleString()}</p>
                </div>
                <div className="rounded-lg bg-brand-cream/[0.03] p-3 border border-brand-cream/5">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">
                    Recovery Range
                  </p>
                  <p className="font-bold text-lg text-foreground">
                    {opp.recoverable_range_sar?.low?.currency} {opp.recoverable_range_sar?.low?.value?.toLocaleString()} – {opp.recoverable_range_sar?.high?.value?.toLocaleString()}
                  </p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <span
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-brand-cream/10 text-brand-cream/70"
                >
                  Confidence: <span className="font-bold">{opp.confidence}</span>
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}