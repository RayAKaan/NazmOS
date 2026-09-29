"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

interface EvidenceRecord {
  evidence_id: string;
  source_type: string;
  source_ref: Record<string, any>;
  calculation: Record<string, any> | null;
  timestamp: string;
}

interface EvidenceViewerProps {
  evidence: Record<string, any>;
  isLoading: boolean;
}

const sourceTypeColors: Record<string, string> = {
  source_row: "bg-accent-blue/20 text-accent-blue border-accent-blue/30",
  calculation: "bg-accent-green/20 text-accent-green border-accent-green/30",
  cross_column: "bg-accent-purple/20 text-accent-purple border-accent-purple/30",
};

export function EvidenceViewer({ evidence, isLoading }: EvidenceViewerProps) {
  if (isLoading) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Evidence Registry
        </h3>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-surface rounded-lg border border-border p-4 shadow-elevation-1">
              <Skeleton className="h-6 w-1/4 mb-2" />
              <div className="grid grid-cols-3 gap-4">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const records = Object.entries(evidence || {});

  if (records.length === 0) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1 text-center">
        <p className="text-muted-foreground">No evidence records available.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
      <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
        Evidence Registry ({records.length})
      </h3>
      <div className="space-y-3">
        {Object.entries(evidence).map(([evidenceId, record]) => (
          <details key={evidenceId} className="group">
            <summary className="cursor-pointer flex items-center justify-between p-4 bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg">
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm text-brand-cream/70">{evidenceId}</span>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded-full text-xs font-medium",
                    (record.source_type && sourceTypeColors[record.source_type]) ||
                      "bg-muted/20 text-muted-foreground border-border"
                  )}
                >
                  {record.source_type || "calculation"}
                </span>
              </div>
              <svg className="w-4 h-4 text-brand-cream/40 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </summary>
            <div className="mt-4 p-4 bg-brand-cream/[0.02] border border-brand-cream/5 rounded-lg space-y-4">
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
              <div className="flex items-center justify-between pt-2 border-t border-brand-cream/5">
                <span className="text-xs text-brand-cream/50 font-mono">{record.evidence_id}</span>
                <span className="text-xs text-brand-cream/40">{record.timestamp || "Unknown time"}</span>
              </div>
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}