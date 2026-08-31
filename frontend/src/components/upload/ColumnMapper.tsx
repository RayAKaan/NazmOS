"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { CheckCircle, AlertTriangle, ChevronDown, Info } from "lucide-react";
import {
  COLUMN_HELP,
  COLUMN_LABELS,
  INVENTORY_SIGNAL_COLUMNS,
  REQUIRED_COLUMNS,
  SALES_SIGNAL_COLUMNS,
  TARGET_COLUMNS,
  TargetColumn,
} from "@/types/upload";
import { cn } from "@/lib/utils";

interface ColumnMapperProps {
  uploadId: string;
  detectedColumns: Record<string, string>;
  confidenceScores: Record<string, number>;
  unmappedColumns: string[];
  sampleRows: Record<string, unknown>[];
  onConfirm: (mappings: Record<string, string>) => Promise<void>;
  onBack: () => void;
}

function asTarget(value: string): TargetColumn | "" {
  return TARGET_COLUMNS.includes(value as TargetColumn) ? (value as TargetColumn) : "";
}

export function ColumnMapper({
  detectedColumns,
  confidenceScores,
  unmappedColumns,
  sampleRows,
  onConfirm,
  onBack,
}: ColumnMapperProps) {
  const sourceColumns = useMemo(() => {
    const fromRows = sampleRows[0] ? Object.keys(sampleRows[0]) : [];
    return Array.from(new Set([...Object.keys(detectedColumns), ...unmappedColumns, ...fromRows]));
  }, [detectedColumns, sampleRows, unmappedColumns]);

  const [mappings, setMappings] = useState<Record<string, string>>(
    Object.fromEntries(
      sourceColumns.map((source) => [source, asTarget(detectedColumns[source] || "")])
    )
  );
  const [editingColumn, setEditingColumn] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const mappedTargets = useMemo(() => Object.values(mappings).filter(Boolean), [mappings]);
  const hasItemName = REQUIRED_COLUMNS.every((req) => mappedTargets.includes(req));
  const hasSalesSignal = mappedTargets.includes("transaction_at") && SALES_SIGNAL_COLUMNS.some((col) => mappedTargets.includes(col));
  const hasInventorySignal = INVENTORY_SIGNAL_COLUMNS.some((col) => col === "current_stock" && mappedTargets.includes(col));
  const readyToImport = hasItemName && (hasSalesSignal || hasInventorySignal);

  const modeLabel = hasInventorySignal && hasSalesSignal
    ? "Sales + inventory file"
    : hasInventorySignal
      ? "Inventory snapshot"
      : hasSalesSignal
        ? "Sales history"
        : "Needs one more field";

  const getSampleValues = (column: string): unknown[] => {
    return sampleRows.slice(0, 3).map((row) => row[column]).filter((value) => value !== undefined && value !== null && value !== "");
  };

  const handleMappingChange = (sourceColumn: string, targetColumn: TargetColumn) => {
    setMappings((prev) => {
      const updated = { ...prev };

      Object.keys(updated).forEach((source) => {
        if (updated[source] === targetColumn && source !== sourceColumn) {
          updated[source] = "";
        }
      });

      updated[sourceColumn] = targetColumn;
      return updated;
    });
    setEditingColumn(null);
  };

  const removeMapping = (targetColumn: TargetColumn) => {
    setMappings((prev) => {
      const updated = { ...prev };
      Object.keys(updated).forEach((source) => {
        if (updated[source] === targetColumn) updated[source] = "";
      });
      return updated;
    });
    setEditingColumn(null);
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      const cleanMappings = Object.fromEntries(Object.entries(mappings).filter(([, target]) => Boolean(target)));
      await onConfirm(cleanMappings);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return "text-success";
    if (confidence >= 0.7) return "text-warning";
    return "text-destructive";
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-primary">Step 2 · Confirm columns</p>
          <h2 className="mt-2 text-2xl font-black text-foreground">Tell NazmOS what each column means</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            We guessed the columns. You only need <b className="text-foreground">Product name</b> plus either
            <b className="text-foreground"> Current stock</b> for an inventory file, or
            <b className="text-foreground"> Sale date + price/total</b> for a sales file.
          </p>
        </div>
        <button
          onClick={onBack}
          className="rounded-xl border border-brand-cream/10 px-4 py-2 text-sm font-bold text-muted-foreground hover:bg-brand-cream/5 hover:text-foreground"
        >
          Back to upload
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className={cn("rounded-2xl border p-4", hasItemName ? "border-success/30 bg-success/10" : "border-destructive/30 bg-destructive/10")}>
          <p className="text-sm font-bold text-foreground">1. Product names</p>
          <p className="mt-1 text-xs text-muted-foreground">{hasItemName ? "Mapped" : "Required before import"}</p>
        </div>
        <div className={cn("rounded-2xl border p-4", hasInventorySignal ? "border-success/30 bg-success/10" : "border-brand-cream/10 bg-brand-cream/[0.03]")}>
          <p className="text-sm font-bold text-foreground">2A. Inventory snapshot</p>
          <p className="mt-1 text-xs text-muted-foreground">Current stock column</p>
        </div>
        <div className={cn("rounded-2xl border p-4", hasSalesSignal ? "border-success/30 bg-success/10" : "border-brand-cream/10 bg-brand-cream/[0.03]")}>
          <p className="text-sm font-bold text-foreground">2B. Sales history</p>
          <p className="mt-1 text-xs text-muted-foreground">Sale date + price or total</p>
        </div>
      </div>

          <div className="overflow-hidden rounded-2xl bg-card ring-1 ring-brand-cream/10">
        <div className="border-b border-border p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2">
              {readyToImport ? (
                <CheckCircle size={18} className="text-success" />
              ) : (
                <AlertTriangle size={18} className="text-warning" />
              )}
              <span className="text-sm font-medium text-foreground">
                {readyToImport ? `Ready: ${modeLabel}` : "Map the minimum fields to continue"}
              </span>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full bg-brand-amber/10 px-3 py-1 text-xs font-bold text-brand-amber">
              <Info className="h-3.5 w-3.5" /> Unneeded columns are ignored safely
            </div>
          </div>
        </div>

        <div className="divide-y divide-border">
          {TARGET_COLUMNS.map((targetCol) => {
            const mappedSource = Object.entries(mappings).find(([, target]) => target === targetCol)?.[0];
            const sampleValues = mappedSource ? getSampleValues(mappedSource) : [];
            const confidence = mappedSource ? confidenceScores[mappedSource] || 0 : 0;
            const isRequired = targetCol === "item_name";
            const isCoreSignal = targetCol === "current_stock" || targetCol === "transaction_at" || targetCol === "unit_price" || targetCol === "total_amount";

            return (
              <div key={targetCol} className="p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">{COLUMN_LABELS[targetCol]}</span>
                      {isRequired && <span className="rounded bg-destructive/20 px-2 py-0.5 text-xs text-destructive">Required</span>}
                      {isCoreSignal && !isRequired && <span className="rounded bg-brand-amber/15 px-2 py-0.5 text-xs text-brand-amber">Audit signal</span>}
                      {mappedSource && (
                        <span className={cn("text-xs", getConfidenceColor(confidence))}>
                          {confidence ? `${Math.round(confidence * 100)}% guess` : "manual"}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{COLUMN_HELP[targetCol]}</p>
                  </div>

                  <div className="relative md:min-w-[260px]">
                    <button
                      onClick={() => setEditingColumn(editingColumn === targetCol ? null : targetCol)}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                        mappedSource
                          ? "bg-secondary/20 text-secondary"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <span className="truncate">{mappedSource || "Select source column"}</span>
                      <ChevronDown size={14} />
                    </button>

                    {editingColumn === targetCol && (
                      <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="absolute right-0 top-full z-20 mt-2 max-h-72 w-full overflow-y-auto rounded-xl border border-border bg-popover shadow-2xl"
                      >
                        {sourceColumns.map((sourceCol) => {
                          const usedBy = Object.entries(mappings).find(([source, target]) => source !== sourceCol && target === targetCol)?.[0];
                          const alreadyMappedTo = mappings[sourceCol];
                          return (
                            <button
                              key={sourceCol}
                              onClick={() => handleMappingChange(sourceCol, targetCol)}
                              className={cn(
                                "flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm hover:bg-muted",
                                mappedSource === sourceCol && "bg-secondary/20"
                              )}
                            >
                              <span className="truncate text-foreground">{sourceCol}</span>
                              <span className="shrink-0 text-xs text-muted-foreground">
                                {alreadyMappedTo && alreadyMappedTo !== targetCol ? COLUMN_LABELS[alreadyMappedTo as TargetColumn] || "mapped" : usedBy ? "in use" : ""}
                              </span>
                            </button>
                          );
                        })}
                        <button
                          onClick={() => removeMapping(targetCol)}
                          className="w-full border-t border-border px-4 py-2.5 text-left text-sm text-destructive hover:bg-muted"
                        >
                          Remove mapping
                        </button>
                      </motion.div>
                    )}
                  </div>
                </div>

                {mappedSource && sampleValues.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {sampleValues.map((val, i) => (
                      <span key={`${mappedSource}-${i}`} className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                        {String(val).slice(0, 38)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-4 text-sm leading-6 text-muted-foreground">
        <b className="text-foreground">Founder tip:</b> If you are not sure, import anyway after the minimum fields.
        NazmOS will ignore extra columns and you can upload a corrected file later. Cost price improves trapped-cash accuracy.
      </div>

      <div className="flex flex-col-reverse gap-3 md:flex-row md:justify-end">
        <button
          onClick={onBack}
          className="rounded-xl px-6 py-3 text-sm font-bold text-muted-foreground hover:text-foreground"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={!readyToImport || isSubmitting}
          className={cn(
            "rounded-xl px-6 py-3 text-sm font-bold transition-colors",
            readyToImport && !isSubmitting
              ? "bg-brand-amber text-brand-night hover:bg-brand-gold"
              : "cursor-not-allowed bg-muted text-muted-foreground"
          )}
        >
          {isSubmitting ? "Starting import..." : "Import for Money Audit"}
        </button>
      </div>
    </motion.div>
  );
}
