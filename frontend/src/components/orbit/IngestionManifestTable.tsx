"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

interface IngestionManifest {
  file_id: string;
  filename: string;
  classification: string;
  confidence: number;
  rows: number;
  columns: number;
  mapped_fields: Record<string, string>;
  missing_fields: string[];
  ambiguous_fields: string[];
  quality: {
    duplicate_rows: number;
    null_rate: number;
    invalid_dates: number;
  };
  metadata: Record<string, any>;
  file_type: string;
  selected_sheet: string | null;
  sheet_count: number | null;
  header_row_index: number | null;
  detected_columns: string[];
  column_confidence: number;
  is_arabic_headers: boolean;
  is_arabic_data: boolean;
}

interface IngestionManifestTableProps {
  manifests: any[];
  isLoading: boolean;
}

const classificationColors: Record<string, string> = {
  SALES: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  INVENTORY: "bg-green-500/20 text-green-400 border-green-500/30",
  PRODUCT_CATALOG: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  PURCHASES: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  SUPPLIERS: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  EXPENSES: "bg-red-500/20 text-red-400 border-red-500/30",
  PAYMENTS: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  CUSTOMERS: "bg-pink-500/20 text-pink-400 border-pink-500/30",
  BRANCHES: "bg-indigo-500/20 text-indigo-400 border-indigo-500/30",
  WASTAGE: "bg-red-500/20 text-red-400 border-red-500/30",
  UNKNOWN: "bg-muted/20 text-muted-foreground border-border",
};

export function IngestionManifestTable({ manifests, isLoading }: IngestionManifestTableProps) {
  if (isLoading) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Ingestion Manifests
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

  if (!manifests || manifests.length === 0) {
    return (
      <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1 text-center">
        <p className="text-muted-foreground">No files uploaded yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
      <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
        Ingestion Manifests ({manifests.length})
      </h3>
      <div className="space-y-3">
        {manifests.map((manifest, index) => (
          <div
            key={manifest.file_id || index}
            className="bg-brand-cream/[0.03] border border-brand-cream/5 rounded-lg p-4"
          >
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-3">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-brand-cream/70">
                    {manifest.filename}
                  </span>
                  <span
                    className={cn(
                      "px-2 py-1 rounded-full text-xs font-medium",
                      (manifest.classification && classificationColors[manifest.classification]) ||
                        classificationColors.UNKNOWN
                    )}
                  >
                    {manifest.classification}
                  </span>
                  <span
                    className="px-2 py-0.5 rounded-full text-xs font-medium bg-brand-cream/10 text-brand-cream/70"
                  >
                    {Math.round(manifest.confidence * 100)}%
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm text-brand-cream/60">
                  <span>{manifest.rows.toLocaleString()} rows</span>
                  <span>{manifest.columns} cols</span>
                  <span>{manifest.file_type?.toUpperCase()}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{manifest.rows.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">Rows</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{manifest.columns}</p>
                  <p className="text-xs text-muted-foreground">Columns</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{manifest.quality?.duplicate_rows || 0}</p>
                  <p className="text-xs text-muted-foreground">Duplicates</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{(manifest.quality?.null_rate * 100).toFixed(1)}%</p>
                  <p className="text-xs text-muted-foreground">Null Rate</p>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{manifest.quality?.invalid_dates || 0}</p>
                  <p className="text-xs text-muted-foreground">Invalid Dates</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{manifest.missing_fields?.length || 0}</p>
                  <p className="text-xs text-muted-foreground">Missing Fields</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{manifest.ambiguous_fields?.length || 0}</p>
                  <p className="text-xs text-muted-foreground">Ambiguous</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-brand-cream/[0.03] border border-brand-cream/5">
                  <p className="text-2xl font-bold text-foreground">{Math.round(manifest.confidence * 100)}%</p>
                  <p className="text-xs text-muted-foreground">Confidence</p>
                </div>
              </div>

              <details className="group">
                <summary className="cursor-pointer flex items-center gap-2 text-sm text-brand-cream/70 hover:text-brand-cream">
                  <span className="font-mono text-xs">Mapped Fields</span>
                  <svg className="w-4 h-4 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div className="mt-3 p-3 rounded-lg bg-brand-cream/[0.02] border border-brand-cream/5">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {Object.entries(manifest.mapped_fields || {}).map(([role, column]: [string, any]) => (
                      <div key={role} className="flex items-center justify-between py-1 border-b border-brand-cream/5 last:border-0">
                        <span className="text-sm font-medium text-brand-cream/70 capitalize">{role.replace(/_/g, " ")}</span>
                        <span className="text-sm font-mono text-brand-cream/50 truncate max-w-[200px]">{column}</span>
                      </div>
                    ))}
                  </div>
                  {Object.keys(manifest.mapped_fields || {}).length === 0 && (
                    <p className="text-sm text-brand-cream/50">No fields mapped</p>
                  )}
                  </div>
                </details>
              </div>

              {manifest.missing_fields?.length > 0 && (
                <details className="group mt-3">
                  <summary className="cursor-pointer flex items-center gap-2 text-sm text-brand-amber/80 hover:text-brand-amber">
                    <span className="font-mono text-xs">Missing Fields ({manifest.missing_fields.length})</span>
                    <svg className="w-4 h-4 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </summary>
                  <div className="mt-3 p-3 rounded-lg bg-brand-amber/10 border border-brand-amber/20">
                    <ul className="space-y-1">
                      {manifest.missing_fields.map((field: string, i: number) => (
                        <li key={i} className="text-sm text-brand-amber/80 flex items-center gap-2">
                          <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brand-amber/20 text-brand-amber text-xs font-bold">
                            M
                          </span>
                          <span>{field}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </details>
              )}

              {manifest.ambiguous_fields?.length > 0 && (
                <details className="group mt-3">
                  <summary className="cursor-pointer flex items-center gap-2 text-sm text-brand-cream/60 hover:text-brand-cream/80">
                    <span className="font-mono text-xs">Ambiguous Fields ({manifest.ambiguous_fields.length})</span>
                    <svg className="w-4 h-4 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </summary>
                  <div className="mt-3 p-3 rounded-lg bg-brand-cream/10 border border-brand-cream/10">
                    <ul className="space-y-1">
                      {manifest.ambiguous_fields.map((field: string, i: number) => (
                        <li key={i} className="text-sm text-brand-cream/60 flex items-center gap-2">
                          <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brand-cream/20 text-brand-cream/70 text-xs font-bold">
                            A
                          </span>
                          <span>{field}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </details>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }