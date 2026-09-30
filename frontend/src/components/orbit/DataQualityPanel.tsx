"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

interface DataQualityModel {
  overall_score: number;
  domain_scores: Record<string, number>;
  missing_required_fields: string[];
  ambiguous_fields: string[];
}

interface DataQualityPanelProps {
  dataQuality: DataQualityModel | null;
  isLoading: boolean;
}

const getScoreColor = (score: number) => {
  if (score >= 70) return "text-accent-green";
  if (score >= 50) return "text-accent-yellow";
  return "text-accent-red";
};

const getScoreBg = (score: number) => {
  if (score >= 70) return "bg-accent-green/10 border-accent-green/30";
  if (score >= 50) return "bg-accent-yellow/10 border-accent-yellow/30";
  return "bg-accent-red/10 border-accent-red/30";
};

const domainLabels: Record<string, string> = {
  sales: "Sales History",
  inventory: "Inventory Coverage",
  cost: "Cost Coverage",
  price: "Selling Price Coverage",
  product_matching: "Product Matching",
  date_coverage: "Date Coverage",
  purchases: "Procurement Data",
  expenses: "Expense Data",
  suppliers: "Supplier Data",
};

export function DataQualityPanel({ dataQuality, isLoading }: DataQualityPanelProps) {
  if (isLoading || !dataQuality) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Data Quality
        </h3>
        <Skeleton className="h-8 w-1/3 mb-4" />
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Data Quality
        </h3>
        <div
          className={cn(
            "px-3 py-1 rounded-full text-sm font-medium",
            getScoreBg(dataQuality.overall_score)
          )}
        >
          {dataQuality.overall_score}/100
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4 mb-6">
        {Object.entries(dataQuality.domain_scores).map(([domain, score]) => (
          <div
            key={domain}
            className="text-center p-4 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5"
          >
            <p className="text-2xl font-bold text-foreground">{score}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {domainLabels[domain] || domain}
            </p>
          </div>
        ))}
      </div>

      {(dataQuality.missing_required_fields?.length || dataQuality.ambiguous_fields?.length) && (
        <div className="mt-6 p-4 rounded-lg bg-brand-amber/10 border border-accent-yellow/30">
          <h4 className="text-sm font-medium text-brand-amber flex items-center gap-2 mb-2">
            <span className="relative flex h-5 w-5">
              <svg className="h-5 w-5 text-brand-amber" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </span>
            <span className="font-medium">Data gaps detected</span>
          </h4>
          <ul className="mt-2 space-y-1 text-sm text-brand-cream/80">
            {dataQuality.missing_required_fields?.map((field, i) => (
              <li key={`missing-${i}`} className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brand-amber/20 text-brand-amber text-xs font-bold">
                  M
                </span>
                <span>Missing required: {field}</span>
              </li>
            ))}
            {dataQuality.ambiguous_fields?.map((field, i) => (
              <li key={`ambiguous-${i}`} className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brand-cream/20 text-brand-cream/70 text-xs font-bold">
                  A
                </span>
                <span>Ambiguous: {field}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6 text-center">
        <p className="text-sm text-muted-foreground">
          Data quality is calculated from uploaded files. Upload purchase history and expenses to improve score.
        </p>
      </div>
    </div>
  );
}