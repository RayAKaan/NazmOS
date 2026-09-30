"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

interface Finding {
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

interface FindingDrilldownProps {
  finding: Finding | null;
  products: any[];
  evidence: any[];
  source_rows: any[];
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

export function FindingDrilldown({ finding, products, evidence, source_rows, isLoading }: FindingDrilldownProps) {
  if (isLoading) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Finding Details
        </h3>
        <div className="space-y-4">
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </div>
    );
  }

  if (!finding) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1 text-center">
        <p className="text-muted-foreground">Select a finding to view details.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Finding Details
          </h3>
          <h2 className="text-xl font-bold text-foreground">{finding.what}</h2>
        </div>
        <div className="flex items-center gap-2">
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

      <div className="space-y-6">
        <div className="bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg p-5">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
            What Happened
          </h4>
          <p className="text-brand-cream/80 leading-relaxed">{finding.what}</p>
        </div>

        <div className="bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg p-5">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
            Why
          </h4>
          <p className="text-brand-cream/80 leading-relaxed">{finding.why}</p>
        </div>

        <div className="bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg p-5">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
            Financial Impact
          </h4>
          <div className="grid md:grid-cols-4 gap-4 mb-4">
            <div className="text-center p-4 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
              <p className="text-2xl font-bold text-foreground">
                {finding.financial_impact?.currency} {finding.financial_impact?.value?.toLocaleString()}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Financial Impact</p>
            </div>
            <div className="text-center p-4 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
              <p className="text-xl font-bold text-foreground">{finding.confidence}</p>
              <p className="text-xs text-muted-foreground mt-1">Confidence</p>
            </div>
            <div className="text-center p-4 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
              <p className="text-xl font-bold text-foreground">{finding.period}</p>
              <p className="text-xs text-muted-foreground mt-1">Period</p>
            </div>
            <div className="text-center p-4 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
              <p className="text-xl font-bold text-foreground">{finding.financial_impact?.basis}</p>
              <p className="text-xs text-muted-foreground mt-1">Basis</p>
            </div>
          </div>
        </div>

        <div className="bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg p-5">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
            Recommended Next Step
          </h4>
          <p className="text-brand-cream/80">{finding.recommended_next_step}</p>
        </div>

        {finding.missing_data?.length > 0 && (
          <div className="rounded-lg p-4 bg-brand-amber/10 border border-accent-yellow/30">
            <h4 className="text-sm font-medium text-brand-amber flex items-center gap-2 mb-3">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span className="font-medium">Missing Data</span>
            </h4>
            <ul className="mt-2 space-y-1 text-sm text-brand-cream/80">
              {finding.missing_data.map((item, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brand-amber/20 text-brand-amber text-xs font-bold">
                    ?
                  </span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="border-t border-brand-cream/10 pt-6">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
            Affected Products
          </h4>
          <div className="space-y-2">
            {products.slice(0, 10).map((product, i) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand-cream/10 text-brand-cream/60 text-xs font-bold">
                    {i + 1}
                  </span>
                  <span className="font-medium text-foreground">{product.name || "Unknown"}</span>
                  {product.evidence_id && (
                    <span className="px-2 py-0.5 rounded-full text-xs font-mono text-brand-cream/50 bg-brand-cream/10">
                      {product.evidence_id}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {products.length > 10 && (
              <p className="text-sm text-brand-cream/50 text-center mt-2">
                +{products.length - 10} more products
              </p>
            )}
          </div>
        </div>

        <div className="border-t border-brand-cream/10 pt-6">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
            Evidence Records
          </h4>
          <div className="space-y-3">
            {evidence.slice(0, 10).map((record, i) => (
              <div key={i} className="group">
                <div className="cursor-pointer flex items-center justify-between p-4 bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm text-brand-cream/70">{record.evidence_id}</span>
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-accent-blue/20 text-accent-blue border-accent-blue/30">
                      {record.source_type}
                    </span>
                  </div>
                  <svg className="w-4 h-4 text-brand-cream/40 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
                <div className="mt-4 p-4 bg-brand-cream/[0.02] border border-brand-cream/5 rounded-lg space-y-4 hidden group-open:block">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Source Reference</p>
                      <pre className="bg-brand-night/50 border border-brand-cream/10 rounded-lg p-3 text-xs font-mono text-brand-cream/80 overflow-x-auto max-h-48 overflow-y-auto">
                        {JSON.stringify(record.source_ref, null, 2)}
                      </pre>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Calculation</p>
                      <pre className="bg-brand-night/50 border border-brand-cream/10 rounded-lg p-3 text-xs font-mono text-brand-cream/80 overflow-x-auto max-h-48 overflow-y-auto">
                        {record.calculation ? JSON.stringify(record.calculation, null, 2) : "No calculation details"}
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {evidence.length > 10 && (
              <p className="text-sm text-brand-cream/50 text-center mt-2">
                +{evidence.length - 10} more evidence records
              </p>
            )}
          </div>
        </div>

        <div className="border-t border-brand-cream/10 pt-6">
          <h4 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
            Source Rows
          </h4>
          <div className="space-y-3">
            {source_rows.slice(0, 5).map((row, i) => (
              <div key={i} className="bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg p-4">
                <pre className="text-xs font-mono text-brand-cream/70 overflow-x-auto">
                  {JSON.stringify(row, null, 2)}
                </pre>
              </div>
            ))}
            {source_rows.length > 5 && (
              <p className="text-sm text-brand-cream/50 text-center">
                +{source_rows.length - 5} more source rows
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}