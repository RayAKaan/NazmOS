"use client";

import { cn } from "@/lib/utils";

interface FindingEvidence {
  what: string;
  why: string;
  financial_impact: {
    value: number;
    currency: string;
    basis: string;
    period: string;
    confidence: string;
    evidence_ids: string[];
  };
  confidence: string;
  period: string;
  evidence_ids: string[];
  recommended_next_step: string;
  missing_data: string[];
}

interface FindingCardProps {
  finding: FindingEvidence;
  onClick?: () => void;
}

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

const formatCurrency = (value: number, currency = "SAR") => {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const categoryIcons: Record<string, string> = {
  INVENTORY: "📦",
  MARGIN: "📊",
  SALES: "💰",
  PROCUREMENT: "🤝",
  CASH: "💵",
  DATA_QUALITY: "🔍",
  OPERATIONS: "⚙️",
  BRANCH: "🏪",
  COMPLIANCE: "⚖️",
};

export function FindingCard({ finding, onClick }: FindingCardProps) {
  const category = finding.evidence_ids[0]?.split("-")[1]?.toUpperCase() || "UNKNOWN";
  const icon = categoryIcons[finding.evidence_ids[0]?.split("-")[1]?.toUpperCase() || ""] || "📋";

  return (
    <div
      onClick={onClick}
      className="bg-surface rounded-lg border border-border p-4 shadow-elevation-1 hover:shadow-elevation-2 transition-all cursor-pointer hover:border-brand-cream/20"
    >
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{finding.evidence_ids[0]?.split("-")[1] || "📋"}</span>
          <div className="flex-1 min-w-0">
            <h4 className="font-semibold text-lg text-foreground truncate">
              {finding.what}
            </h4>
            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{finding.why}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span
            className={cn(
              "px-2 py-1 rounded-full text-xs font-bold",
              finding.confidence === "HIGH"
                ? "bg-accent-green/10 text-accent-green border-accent-green/30"
                : finding.confidence === "MEDIUM"
                ? "bg-accent-yellow/10 text-accent-yellow border-accent-yellow/30"
                : "bg-accent-red/10 text-accent-red border-accent-red/30"
            )}
          >
            {finding.confidence}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-muted-foreground mb-1">Financial Impact</p>
<div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-foreground">
                {finding.financial_impact?.currency} {finding.financial_impact?.value?.toLocaleString()}
              </span>
              <span className="text-sm text-muted-foreground">{finding.financial_impact?.period}</span>
            </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span
            className={cn(
              "px-2 py-1 rounded-full text-xs font-bold",
              finding.confidence === "HIGH"
                ? "bg-accent-green/10 text-accent-green border-accent-green/30"
                : finding.confidence === "MEDIUM"
                ? "bg-accent-yellow/10 text-accent-yellow border-accent-yellow/30"
                : "bg-accent-red/10 text-accent-red border-accent-red/30"
            )}
          >
            {finding.confidence}
          </span>
        </div>
      </div>

      <div className="border-t border-brand-cream/10 pt-3">
        <p className="text-sm text-muted-foreground mb-2">Recommended: {finding.recommended_next_step}</p>
        {finding.missing_data?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {finding.missing_data.map((item, i) => (
              <span key={i} className="px-2 py-0.5 rounded-full text-xs font-medium bg-brand-amber/20 text-brand-amber/80 border border-brand-amber/30">
                Missing: {item}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}