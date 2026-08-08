"use client";

import { useState, useCallback, DragEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { UploadCloud, FileSpreadsheet, RefreshCw, ArrowRight, CheckCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { detectSchemaFromCSV } from "@/lib/schema-detector";
import api from "@/lib/api";

interface GuestAuditSummary {
  money_at_risk_sar: number;
  dead_stock_value_sar: number;
  stockout_risk_value_sar: number;
  margin_leakage_sar: number;
  overstock_value_sar: number;
  action_count: number;
  row_count: number;
  confidence_score: number;
  guest_session_id: string;
}

interface GuestAuditAction {
  action_type: string;
  title: string;
  description: string;
  expected_recovery_sar: number;
  priority: number;
}

interface GuestAuditResult {
  summary: GuestAuditSummary;
  actions: GuestAuditAction[];
  missing_data: { code: string; message: string }[];
}

const MAX_FILE_SIZE = 2 * 1024 * 1024;

export function GuestAuditUploader() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState<"idle" | "scanning" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<GuestAuditResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detectedKind, setDetectedKind] = useState<string | null>(null);

  const validateFile = (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["csv", "xlsx", "xls"].includes(ext)) {
      return "Upload CSV or Excel only.";
    }
    if (file.size > MAX_FILE_SIZE) {
      return "File is too large. Free preview supports up to 2 MB.";
    }
    return null;
  };

  const runAudit = useCallback(async (uploadFile: File) => {
    const validationError = validateFile(uploadFile);
    if (validationError) {
      setError(validationError);
      setStatus("error");
      return;
    }

    setStatus("scanning");
    setError(null);

    try {
      if (uploadFile.name.toLowerCase().endsWith(".csv")) {
        const detection = await detectSchemaFromCSV(uploadFile);
        setDetectedKind(detection.suggested_file_kind || null);
      }

      setStatus("running");

      const Papa = (await import("papaparse")).default;
      const parsed = await new Promise<Record<string, unknown>[]>((resolve) => {
        Papa.parse(uploadFile, {
          header: true,
          skipEmptyLines: true,
          complete: (r) => resolve(r.data as Record<string, unknown>[]),
        });
      });

      const response = await api.post("/guest-audit", { rows: parsed });
      setResult(response.data);
      setStatus("done");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not run preview audit. Try a different file.");
      setStatus("error");
    }
  }, []);

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) {
      setFile(dropped);
      runAudit(dropped);
    }
  };

  const reset = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setDetectedKind(null);
    setStatus("idle");
  };

  const money = (value?: number) =>
    `SAR ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <AnimatePresence mode="wait">
        {status === "idle" && (
          <motion.div
            key="idle"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
          >
            <label
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onDrop}
              className="block cursor-pointer"
            >
              <div
                className={cn(
                  "flex flex-col items-center justify-center rounded-3xl border-2 border-dashed p-8 text-center transition-all md:p-10",
                  isDragging
                    ? "border-[#E0B34A] bg-[#E0B34A]/10"
                    : "border-white/15 bg-white/[0.04] hover:border-[#E0B34A]/60 hover:bg-white/[0.06]"
                )}
              >
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      setFile(f);
                      runAudit(f);
                    }
                  }}
                />
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#E0B34A]/15">
                  <UploadCloud className="h-8 w-8 text-[#E0B34A]" />
                </div>
                <h3 className="text-xl font-bold text-white">Drop your sales or inventory file</h3>
                <p className="mt-2 text-sm text-white/55">CSV or Excel · max 2 MB · no sign-up required</p>
                <div className="mt-6 flex flex-wrap justify-center gap-2 text-xs text-white/40">
                  <span className="rounded-full bg-white/5 px-3 py-1">product name</span>
                  <span className="rounded-full bg-white/5 px-3 py-1">quantity / stock</span>
                  <span className="rounded-full bg-white/5 px-3 py-1">price / cost</span>
                </div>
              </div>
            </label>
          </motion.div>
        )}

        {(status === "scanning" || status === "running") && (
          <motion.div
            key="running"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="rounded-3xl border border-white/10 bg-[#0A0E0C] p-10 text-center text-white"
          >
            <div className="mx-auto mb-5 flex h-16 w-16 animate-pulse items-center justify-center rounded-full bg-[#E0B34A]/15">
              <RefreshCw className="h-7 w-7 animate-spin text-[#E0B34A]" />
            </div>
            <h3 className="text-xl font-bold">
              {status === "scanning" ? "Scanning columns…" : "Finding trapped cash…"}
            </h3>
            <p className="mt-2 text-sm text-white/55">
              {file ? file.name : ""} · This usually takes under 10 seconds
            </p>
          </motion.div>
        )}

        {status === "done" && result && (
          <motion.div
            key="done"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="overflow-hidden rounded-3xl border border-[#13A05A]/30 bg-[#0A0E0C] text-white shadow-2xl"
          >
            <div className="bg-[#13A05A]/10 p-6 md:p-8">
              <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="font-mono text-xs uppercase tracking-[0.24em] text-[#9ff2bd]">Free preview result</p>
                  <h3 className="mt-2 font-serif text-3xl font-black md:text-4xl">
                    {money(result.summary.money_at_risk_sar)} is at risk
                  </h3>
                  <p className="mt-2 text-sm text-white/60">
                    Based on {result.summary.row_count.toLocaleString()} rows · confidence{" "}
                    {Math.round(result.summary.confidence_score)}%
                  </p>
                </div>
                <div className="text-left md:text-right">
                  <p className="text-xs text-white/45">{result.actions.length} recommended action(s)</p>
                </div>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                <Kpi label="Dead stock" value={money(result.summary.dead_stock_value_sar)} tone="red" />
                <Kpi label="Stockout risk" value={money(result.summary.stockout_risk_value_sar)} tone="gold" />
                <Kpi label="Margin leakage" value={money(result.summary.margin_leakage_sar)} tone="green" />
              </div>
            </div>

            <div className="p-6 md:p-8">
              <h4 className="text-sm font-bold uppercase tracking-wider text-white/55">Top actions</h4>
              <div className="mt-4 space-y-3">
                {result.actions.slice(0, 3).map((action, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-white/[0.04] p-4 md:flex-row md:items-center md:justify-between"
                  >
                    <div>
                      <p className="font-semibold text-white">{action.title}</p>
                      <p className="mt-1 text-sm leading-5 text-white/55">{action.description}</p>
                    </div>
                    <div className="shrink-0 text-left md:text-right">
                      <p className="text-lg font-black text-[#13A05A]">{money(action.expected_recovery_sar)}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <button
                  onClick={reset}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 px-5 py-3 text-sm font-bold text-white/75 hover:bg-white/5"
                >
                  <RefreshCw className="h-4 w-4" /> Try another file
                </button>
                <a
                  href="/register?intent=free-audit"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#E0B34A] px-5 py-3 text-sm font-bold text-[#0A0E0C] hover:bg-[#f0c765]"
                >
                  Get the full free audit <ArrowRight className="h-4 w-4" />
                </a>
              </div>
            </div>
          </motion.div>
        )}

        {status === "error" && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="rounded-3xl border border-[#C8412A]/30 bg-[#C8412A]/10 p-8 text-center text-white"
          >
            <AlertTriangle className="mx-auto mb-4 h-10 w-10 text-[#ff8a73]" />
            <h3 className="text-lg font-bold">Could not run preview</h3>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-white/65">{error}</p>
            <button
              onClick={reset}
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#E0B34A] px-5 py-3 text-sm font-bold text-[#0A0E0C] hover:bg-[#f0c765]"
            >
              <RefreshCw className="h-4 w-4" /> Try again
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: "red" | "gold" | "green" }) {
  const colors = {
    red: "text-[#ff8a73]",
    gold: "text-[#E0B34A]",
    green: "text-[#13A05A]",
  };
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <p className="text-xs uppercase tracking-wider text-white/45">{label}</p>
      <p className={cn("mt-1 font-serif text-2xl font-black", colors[tone])}>{value}</p>
    </div>
  );
}
