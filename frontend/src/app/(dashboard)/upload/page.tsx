"use client";

import { useState, useCallback, DragEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle,
  Database,
  FileSpreadsheet,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import { ColumnMapper } from "@/components/upload/ColumnMapper";
import { UploadResult, IngestionProgress, IngestionResult } from "@/types/upload";
import { useAppStore } from "@/stores/appStore";
import api from "@/lib/api";
import { FreeAuditChecklist } from "@/components/free/FreeAuditChecklist";
import { cn } from "@/lib/utils";
import { detectSchemaFromCSV } from "@/lib/schema-detector";

const CLIENT_ETL = process.env.NEXT_PUBLIC_CLIENT_ETL === "true";

type UploadStep = "upload" | "mapping" | "processing" | "success" | "error";

const stepOrder: UploadStep[] = ["upload", "mapping", "processing", "success"];
const stepLabels: Record<UploadStep, string> = {
  upload: "Upload",
  mapping: "Confirm columns",
  processing: "Import",
  success: "Money Audit ready",
  error: "Fix issue",
};

function getApiErrorMessage(err: unknown, fallback: string) {
  const anyErr = err as any;
  const detail = anyErr?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (anyErr?.message) return anyErr.message;
  return fallback;
}

function normalizeProgress(data: any, fallbackTotal = 0): IngestionProgress {
  const rowsProcessed = Number(data?.rows_processed ?? data?.row_count_imported ?? 0);
  const totalRows = Number(data?.total_rows ?? data?.row_count_raw ?? fallbackTotal ?? rowsProcessed);
  return {
    upload_id: String(data?.upload_id || ""),
    status: data?.status || "processing",
    progress: Number(data?.progress ?? (data?.status === "completed" ? 100 : 65)),
    rows_processed: rowsProcessed,
    total_rows: totalRows,
    errors: Array.isArray(data?.errors) ? data.errors : [],
    started_at: data?.started_at || null,
    estimated_completion: data?.estimated_completion || null,
  };
}

function fallbackResult(uploadId: string, progress: IngestionProgress | null): IngestionResult {
  return {
    upload_id: uploadId,
    status: progress?.errors?.length ? "partial" : "completed",
    rows_imported: progress?.rows_processed || 0,
    rows_failed: progress?.errors?.length || 0,
    errors: progress?.errors || [],
    duration_seconds: 0,
  };
}

export default function UploadPage() {
  const [step, setStep] = useState<UploadStep>("upload");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [ingestionProgress, setIngestionProgress] = useState<IngestionProgress | null>(null);
  const [ingestionResult, setIngestionResult] = useState<IngestionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { businessId } = useAppStore();

  const handleUploadComplete = useCallback((result: UploadResult) => {
    setUploadResult(result);
    setError(null);
    setStep("mapping");
  }, []);

  const pollIngestionStatus = useCallback(async (uploadId: string, fallbackTotal: number, attempt = 0) => {
    try {
      const response = await api.get(`/upload/${uploadId}/status`);
      const progress = normalizeProgress(response.data, fallbackTotal);
      setIngestionProgress(progress);

      if (progress.status === "completed") {
        try {
          const resultResponse = await api.get(`/upload/${uploadId}/result`);
          setIngestionResult(resultResponse.data);
        } catch {
          setIngestionResult(fallbackResult(uploadId, progress));
        }
        setStep("success");
        return;
      }

      if (progress.status === "failed") {
        setStep("error");
        setError(progress.errors?.[0]?.error || "Import failed. Check the file and try again.");
        return;
      }

      if (attempt >= 90) {
        setStep("error");
        setError("Import is taking too long. Make sure the ingestion worker is running, then retry.");
        return;
      }

      window.setTimeout(() => pollIngestionStatus(uploadId, fallbackTotal, attempt + 1), 2000);
    } catch (err) {
      setStep("error");
      setError(getApiErrorMessage(err, "Failed to check import status"));
    }
  }, []);

  const handleMappingConfirm = useCallback(async (mappings: Record<string, string>) => {
    if (!uploadResult || !businessId) {
      setError("Business account is still loading. Refresh and try again.");
      setStep("error");
      return;
    }

    setStep("processing");
    setError(null);

    // Client ETL path: send parsed JSON rows directly to /ingest-json
    if (CLIENT_ETL && (uploadResult as any)._clientParsed) {
      try {
        const response = await api.post("/upload/ingest-json", {
          business_id: businessId,
          column_mapping: mappings,
          rows: (uploadResult as any)._clientRows,
          filename: uploadResult.filename,
        });

        const result: IngestionResult = {
          upload_id: response.data.upload_id,
          status: response.data.status || "completed",
          rows_imported: response.data.rows_imported || 0,
          rows_failed: response.data.rows_failed || 0,
          errors: response.data.errors || [],
          duration_seconds: response.data.duration_seconds || 0,
        };
        setIngestionResult(result);
        setStep("success");
        return;
      } catch (err) {
        setStep("error");
        setError(getApiErrorMessage(err, "Failed to import data"));
        return;
      }
    }

    // Server ETL path: POST /map + poll
    try {
      const response = await api.post(`/upload/${uploadResult.upload_id}/map`, {
        business_id: businessId,
        column_mapping: mappings,
      });

      setIngestionProgress(normalizeProgress(response.data, uploadResult.row_count));
      pollIngestionStatus(uploadResult.upload_id, uploadResult.row_count);
    } catch (err) {
      setStep("error");
      setError(getApiErrorMessage(err, "Failed to start import"));
    }
  }, [uploadResult, businessId, pollIngestionStatus]);

  const handleReset = () => {
    setStep("upload");
    setUploadResult(null);
    setIngestionProgress(null);
    setIngestionResult(null);
    setError(null);
  };

  const stepIndex = stepOrder.indexOf(step === "error" ? "processing" : step);

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <section className="overflow-hidden rounded-3xl border border-brand-cream/10 bg-brand-night p-6 text-brand-cream shadow-2xl shadow-brand-night/20 md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">Free Money Audit upload</p>
            <h1 className="mt-3 max-w-3xl text-3xl font-black leading-tight md:text-5xl">
              Upload what your POS already gives you.
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-brand-cream/62">
              Sales file + inventory file is best. If you only have one file, start there. NazmOS will map columns,
              import safely, then show trapped cash, stockout risk, and margin leakage.
            </p>
          </div>
          <div className="rounded-2xl border border-brand-green/30 bg-brand-green/10 p-4 text-sm text-whatsapp-light">
            <div className="flex items-center gap-2 font-bold">
              <ShieldCheck className="h-4 w-4" /> User-safe import
            </div>
            <p className="mt-1 text-xs leading-5 text-brand-cream/55">Extra columns are ignored. You can re-upload corrected files anytime.</p>
          </div>
        </div>
      </section>

      <FreeAuditChecklist />

      <div className="flex gap-3 overflow-x-auto rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-3">
        {stepOrder.map((s, i) => (
          <div key={s} className="flex min-w-fit items-center gap-3">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold",
                  step === s
                    ? "bg-brand-amber text-brand-night"
                    : stepIndex > i
                      ? "bg-brand-green text-brand-night"
                      : "bg-muted text-muted-foreground"
                )}
              >
                {stepIndex > i ? <CheckCircle size={16} /> : i + 1}
              </div>
              <span className={cn("text-sm font-bold", step === s ? "text-brand-cream" : "text-muted-foreground")}>{stepLabels[s]}</span>
            </div>
            {i < stepOrder.length - 1 && <div className={cn("h-0.5 w-10", stepIndex > i ? "bg-brand-green" : "bg-muted")} />}
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {step === "upload" && (
          <motion.div key="upload" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <DropZoneWithCallback onUploadComplete={handleUploadComplete} />
          </motion.div>
        )}

        {step === "mapping" && uploadResult && (
          <motion.div key="mapping" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
            <ColumnMapper
              uploadId={uploadResult.upload_id}
              detectedColumns={uploadResult.detected_columns}
              confidenceScores={uploadResult.confidence_scores}
              unmappedColumns={uploadResult.unmapped_columns}
              sampleRows={uploadResult.sample_rows}
              onConfirm={handleMappingConfirm}
              onBack={handleReset}
            />
          </motion.div>
        )}

        {step === "processing" && (
          <motion.div key="processing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="rounded-3xl border border-brand-cream/10 bg-card p-8 text-center">
            <div className="mx-auto mb-6 flex h-16 w-16 animate-pulse items-center justify-center rounded-full bg-brand-amber/10">
              <Database size={24} className="text-brand-amber" />
            </div>
            <h2 className="text-xl font-bold text-foreground">Building your Money Audit dataset</h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
              NazmOS is importing products, stock, and sales rows. This is where the product becomes useful.
            </p>

            {ingestionProgress && (
              <div className="mx-auto mt-6 max-w-md">
                <div className="mb-2 flex justify-between text-sm">
                  <span className="text-muted-foreground">Progress</span>
                  <span className="text-foreground">
                    {ingestionProgress.rows_processed.toLocaleString()} / {ingestionProgress.total_rows.toLocaleString()} rows
                  </span>
                </div>
                <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
                  <motion.div className="h-full rounded-full bg-brand-amber" initial={{ width: 0 }} animate={{ width: `${ingestionProgress.progress}%` }} transition={{ duration: 0.3 }} />
                </div>
                {ingestionProgress.errors.length > 0 && (
                  <p className="mt-4 text-left text-sm text-warning">{ingestionProgress.errors.length} rows need review after import.</p>
                )}
              </div>
            )}
          </motion.div>
        )}

        {step === "success" && ingestionResult && (
          <motion.div key="success" initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="rounded-3xl border border-brand-green/30 bg-brand-night p-8 text-center text-brand-cream">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-brand-green/10">
              <CheckCircle size={24} className="text-brand-green" />
            </div>
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-green">Import complete</p>
            <h2 className="mt-2 text-2xl font-black">Your Money Audit inputs are ready.</h2>
            <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-brand-cream/60">
              Next: open the dashboard to review trapped cash signals, or upload the second file if you only uploaded sales or inventory.
            </p>

            <div className="mx-auto my-8 grid max-w-lg gap-4 sm:grid-cols-3">
              <Metric label="Imported" value={ingestionResult.rows_imported.toLocaleString()} tone="white" />
              <Metric label="Need review" value={ingestionResult.rows_failed.toLocaleString()} tone="yellow" />
              <Metric label="Duration" value={`${ingestionResult.duration_seconds.toFixed(1)}s`} tone="white" />
            </div>

            {ingestionResult.errors.length > 0 && (
              <div className="mx-auto mb-6 max-h-48 max-w-2xl overflow-y-auto rounded-xl bg-brand-cream/[0.04] p-4 text-left ring-1 ring-brand-cream/10">
                <p className="mb-2 text-sm font-bold text-brand-cream">Rows to review:</p>
                {ingestionResult.errors.slice(0, 10).map((err, i) => (
                  <p key={i} className="text-xs leading-5 text-destructive">Row {err.row}: {err.error}</p>
                ))}
                {ingestionResult.errors.length > 10 && <p className="mt-2 text-xs text-muted-foreground">...and {ingestionResult.errors.length - 10} more.</p>}
              </div>
            )}

            <div className="flex flex-col justify-center gap-3 sm:flex-row">
              <button onClick={handleReset} className="inline-flex items-center justify-center gap-2 rounded-xl border border-brand-cream/10 px-6 py-3 font-bold text-brand-cream/75 hover:bg-brand-cream/5">
                <RefreshCw size={16} /> Upload second file
              </button>
              <a href="/dashboard" className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-amber px-6 py-3 font-bold text-brand-night hover:bg-brand-gold">
                Open dashboard <ArrowRight size={16} />
              </a>
            </div>
          </motion.div>
        )}

        {step === "error" && (
          <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="rounded-3xl border border-brand-red/30 bg-brand-red/10 p-8 text-center text-brand-cream">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
              <AlertCircle size={24} className="text-destructive" />
            </div>
            <h2 className="text-xl font-bold">This file needs attention</h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-brand-cream/65">{error}</p>
            <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
              <button onClick={handleReset} className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-amber px-6 py-3 font-bold text-brand-night hover:bg-brand-gold">
                <RefreshCw size={16} /> Try another file
              </button>
              <a href="/product-demo" className="rounded-xl border border-brand-cream/10 px-6 py-3 font-bold text-brand-cream/75 hover:bg-brand-cream/5">See sample format</a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: "white" | "yellow" }) {
  return (
    <div className="rounded-2xl bg-brand-cream/[0.04] p-4 ring-1 ring-brand-cream/10">
      <p className={cn("text-2xl font-black", tone === "yellow" ? "text-brand-amber" : "text-brand-cream")}>{value}</p>
      <p className="mt-1 text-xs text-brand-cream/45">{label}</p>
    </div>
  );
}

function DropZoneWithCallback({ onUploadComplete }: { onUploadComplete: (result: UploadResult) => void }) {
  const { businessId } = useAppStore();
  const [state, setState] = useState<"idle" | "scan" | "preview">("idle");
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const validateFile = (file: File) => {
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!extension || !["csv", "xls", "xlsx"].includes(extension)) {
      return "Upload CSV, XLS, or XLSX only.";
    }
    if (file.size > 15 * 1024 * 1024) {
      return "File is too large. Maximum size is 15 MB.";
    }
    return null;
  };

  const handleFile = async (file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!businessId) {
      setError("Business account is still loading. Refresh and try again.");
      return;
    }

    setState("scan");
    setError(null);

    // Client ETL path: parse CSV in browser
    if (CLIENT_ETL && file.name.toLowerCase().endsWith(".csv")) {
      try {
        const detection = await detectSchemaFromCSV(file);
        const clientResult: UploadResult & { _clientParsed: boolean; _clientRows: Record<string, unknown>[] } = {
          upload_id: `client_${Date.now()}`,
          filename: file.name,
          file_size: file.size,
          mime_type: file.type || "text/csv",
          row_count: detection.row_count,
          detected_columns: detection.detected_columns,
          confidence_scores: detection.confidence_scores,
          unmapped_columns: detection.unmapped_columns,
          sample_rows: detection.sample_rows,
          suggested_file_kind: detection.suggested_file_kind,
          schema_valid: detection.schema_valid,
          _clientParsed: true,
          _clientRows: [], // Will be populated below
        };

        // Re-parse full file for the actual rows
        const Papa = (await import("papaparse")).default;
        const fullParse = await new Promise<Record<string, unknown>[]>((resolve) => {
          Papa.parse(file, {
            header: true,
            skipEmptyLines: true,
            complete(results) {
              resolve(results.data as Record<string, unknown>[]);
            },
          });
        });
        clientResult._clientRows = fullParse;

        setUploadResult(clientResult);
        setState("preview");
      } catch (err) {
        setState("idle");
        setError(getApiErrorMessage(err, "Failed to parse CSV file"));
      }
      return;
    }

    // Server ETL path: multipart upload
    const formData = new FormData();
    formData.append("file", file);
    formData.append("business_id", businessId);

    try {
      const response = await api.post("/upload/", formData, { headers: { "Content-Type": "multipart/form-data" } });
      setUploadResult(response.data);
      setState("preview");
    } catch (err) {
      setState("idle");
      setError(getApiErrorMessage(err, "Upload failed. Try exporting CSV/XLSX again."));
    }
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_.85fr]">
      <div className="rounded-3xl border border-brand-cream/10 bg-card p-6 md:p-8">
        {state === "preview" && uploadResult ? (
          <div className="text-center">
            <CheckCircle size={48} className="mx-auto mb-4 text-brand-green" />
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-brand-green">File scanned</p>
            <h3 className="mt-2 text-xl font-bold text-foreground">{uploadResult.filename}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {uploadResult.row_count.toLocaleString()} rows · {uploadResult.suggested_file_kind === "inventory_snapshot" ? "Looks like inventory" : "Looks like sales"}
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {Object.entries(uploadResult.detected_columns).slice(0, 8).map(([col, mapped]) => (
                <span key={col} className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">{col} → {mapped}</span>
              ))}
            </div>
            <button onClick={() => onUploadComplete(uploadResult)} className="mt-6 rounded-xl bg-brand-amber px-6 py-3 font-bold text-brand-night hover:bg-brand-gold">
              Confirm columns
            </button>
          </div>
        ) : (
          <label
            onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
            className="block cursor-pointer"
          >
            <div className={cn(
              "flex min-h-[280px] flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition-all",
              isDragging ? "border-brand-amber bg-brand-amber/10" : "border-border hover:border-brand-amber/50 hover:bg-brand-amber/5"
            )}>
              <input
                type="file"
                accept=".csv,.xls,.xlsx"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) handleFile(file);
                }}
              />
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted">
                {state === "scan" ? <Database className="h-8 w-8 animate-pulse text-brand-amber" /> : <UploadCloud className="h-8 w-8 text-brand-amber" />}
              </div>
              <p className="mb-2 text-lg font-bold text-foreground">
                {state === "scan" ? "Scanning file..." : "Drop a sales or inventory file here"}
              </p>
              <p className="text-sm leading-6 text-muted-foreground">or click to browse · CSV, XLSX, XLS · max 15 MB</p>
              <p className="mt-3 text-xs text-muted-foreground">Start with one file. Upload the second after import.</p>
            </div>
          </label>
        )}
        {error && <p className="mt-4 rounded-xl bg-destructive/10 p-3 text-center text-sm text-destructive">{error}</p>}
      </div>

      <aside className="rounded-3xl border border-brand-cream/10 bg-brand-night p-6 text-brand-cream">
        <div className="flex items-center gap-2 text-brand-amber">
          <FileSpreadsheet className="h-5 w-5" />
          <p className="font-bold">Best audit quality</p>
        </div>
        <div className="mt-5 space-y-3">
          <Requirement title="Sales history" body="Product name, sale date, sold quantity, sale price or total. 30–90 days is enough." />
          <Requirement title="Inventory snapshot" body="Product name, current stock, cost price, shelf price. Barcode and category improve matching." />
          <Requirement title="Optional but powerful" body="Expiry date, batch number, brand, pack size, storage type for safe Recovery Match later." />
        </div>
        <div className="mt-5 rounded-2xl border border-brand-green/30 bg-brand-green/10 p-4 text-sm leading-6 text-brand-cream/62">
          <b className="text-whatsapp-light">Do not overthink it.</b> Real merchant files are messy. NazmOS now supports manual column correction instead of forcing perfect templates.
        </div>
      </aside>
    </div>
  );
}

function Requirement({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl bg-brand-cream/[0.04] p-4 ring-1 ring-brand-cream/5">
      <p className="font-bold">{title}</p>
      <p className="mt-1 text-sm leading-6 text-brand-cream/55">{body}</p>
    </div>
  );
}
