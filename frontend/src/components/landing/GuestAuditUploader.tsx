"use client";

import { useState, useCallback, DragEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  UploadCloud,
  FileSpreadsheet,
  RefreshCw,
  ArrowRight,
  ArrowLeft,
  AlertTriangle,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useAudit } from "@/components/landing/audit-context";
import type { GuestAuditResult } from "@/components/landing/audit-types";

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ACCEPT = ".csv,.xlsx,.xls,.xlsm,.json";

function pickFirstFile(ev: React.ChangeEvent<HTMLInputElement>): File | null {
  return ev.target.files?.[0] ?? null;
}

export function GuestAuditUploader() {
  const { setResult: setAuditResult } = useAudit();
  const [salesFile, setSalesFile] = useState<File | null>(null);
  const [inventoryFile, setInventoryFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState<"sales" | "inventory" | null>(null);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<GuestAuditResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const validateFile = (file: File): string | null => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["csv", "xlsx", "xls", "xlsm", "json"].includes(ext)) {
      return "Upload CSV or Excel files only.";
    }
    if (file.size > MAX_FILE_SIZE) {
      return "File is too large. The free preview supports up to 10 MB per file.";
    }
    return null;
  };

  const setDrop = (slot: "sales" | "inventory") => (file: File | null) => {
    if (slot === "sales") setSalesFile(file);
    else setInventoryFile(file);
  };

  const onDrop = (slot: "sales" | "inventory") => (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(null);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) setDrop(slot)(dropped);
  };

  const runAudit = useCallback(async () => {
    const fileA = salesFile;
    const fileB = inventoryFile;
    if (!fileA && !fileB) {
      setError("Upload at least one file — sales or inventory.");
      setStatus("error");
      return;
    }

    const errors = [fileA, fileB].filter(Boolean).map((f) => validateFile(f as File)).filter(Boolean);
    if (errors.length) {
      setError(errors[0] as string);
      setStatus("error");
      return;
    }

    setStatus("running");
    setError(null);

    try {
      const form = new FormData();
      if (fileA && fileB) {
        form.append("sales_file", fileA);
        form.append("inventory_file", fileB);
      } else {
        form.append("file", (fileA || fileB) as File);
      }

      const response = await api.post<GuestAuditResult>("/guest-audit", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(response.data);
      setAuditResult(response.data);
      setStatus("done");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not run the free audit. Try different files.");
      setStatus("error");
    }
  }, [salesFile, inventoryFile, setAuditResult]);

  const reset = () => {
    setSalesFile(null);
    setInventoryFile(null);
    setResult(null);
    setError(null);
    setStatus("idle");
  };

  const money = (value?: number) =>
    `SAR ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

  const ready = status === "idle" && (salesFile !== null || inventoryFile !== null);
  const rtl = result?.summary.is_arabic === true;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <AnimatePresence mode="wait">
        {status === "idle" && (
          <motion.div
            key="idle"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="space-y-4"
          >
            <div className="grid gap-4 md:grid-cols-2">
              <FileSlot
                slot="sales"
                label="Upload your sales file"
                hint="CSV or Excel · qty sold, price, date"
                dragging={dragging}
                onDragEnter={setDragging}
                onDrop={onDrop("sales")}
                onChange={(e) => setDrop("sales")(pickFirstFile(e))}
              />
              <FileSlot
                slot="inventory"
                label="Upload your inventory file"
                hint="CSV or Excel · current stock, cost, price"
                dragging={dragging}
                onDragEnter={setDragging}
                onDrop={onDrop("inventory")}
                onChange={(e) => setDrop("inventory")(pickFirstFile(e))}
              />
            </div>

            <div className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.04] p-4 text-sm text-brand-cream/55">
              <Layers className="mr-2 inline h-4 w-4 text-brand-amber" />
              {salesFile && inventoryFile ? (
                <span>
                  Two files paired: <b className="text-brand-cream">{salesFile.name}</b> +{" "}
                  <b className="text-brand-cream">{inventoryFile.name}</b>
                </span>
              ) : salesFile || inventoryFile ? (
                <span>
                  One file selected: <b className="text-brand-cream">{(salesFile || inventoryFile)?.name}</b>.
                  Add the second file to match sales to stock — it is the fastest way to find trapped cash.
                </span>
              ) : (
                <span>Upload either file, or both — no sign-up, no credit card, max 10 MB each.</span>
              )}
            </div>

            <button
              onClick={runAudit}
              disabled={!ready}
              className={cn(
                "inline-flex w-full items-center justify-center gap-2 rounded-xl px-6 py-4 text-base font-bold transition-all",
                ready
                  ? "bg-brand-amber text-brand-night shadow-2xl shadow-brand-amber/20 hover:bg-brand-gold-soft"
                  : "cursor-not-allowed border border-brand-cream/10 text-brand-cream/35"
              )}
            >
              Analyze Free <ArrowRight className="h-5 w-5" />
            </button>
          </motion.div>
        )}

        {status === "running" && (
          <motion.div
            key="running"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="rounded-3xl border border-brand-cream/10 bg-brand-night p-10 text-center text-brand-cream"
          >
            <div className="mx-auto mb-5 flex h-16 w-16 animate-pulse items-center justify-center rounded-full bg-brand-amber/15">
              <RefreshCw className="h-7 w-7 animate-spin text-brand-amber" />
            </div>
            <h3 className="text-xl font-bold">Finding trapped cash…</h3>
            <p className="mt-2 text-sm text-brand-cream/55">
              {[salesFile, inventoryFile].filter(Boolean).map((f) => f?.name).join(" + ")} · usually under 10 seconds
            </p>
          </motion.div>
        )}

        {status === "done" && result && (
          <motion.div
            key="done"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            dir={rtl ? "rtl" : "ltr"}
            className="overflow-hidden rounded-3xl border border-brand-green/30 bg-brand-night text-brand-cream shadow-2xl"
          >
            <div className="bg-brand-green/10 p-6 md:p-8">
              <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="font-mono text-xs uppercase tracking-[0.24em] text-whatsapp-light">Free audit result</p>
                  <h3 className="mt-2 font-serif text-3xl font-black md:text-4xl">
                    {money(result.summary.money_at_risk_sar)} could be tied up in your store
                  </h3>
                  <p className="mt-2 text-sm text-brand-cream/60">
                    Based on {result.summary.row_count.toLocaleString()} rows · confidence{" "}
                    {Math.round(result.summary.confidence_score)}%
                  </p>
                </div>
                <div className="text-left md:text-right" dir="ltr">
                  <p className="text-xs text-brand-cream/45">
                    {result.summary.products_needing_attention ?? result.actions.length} product(s) need an action
                  </p>
                  {result.summary.is_two_file && result.summary.pairing && (
                    <p className="mt-1 text-xs text-brand-cream/45">
                      Sales matched to inventory: {result.summary.pairing.paired}/{result.summary.pairing.attempted}
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <CategoryTile label="Dead stock" value={money(result.summary.dead_stock_value_sar)} tone="red" />
                <CategoryTile label="Overstock" value={money(result.summary.overstock_value_sar)} tone="gold" />
                <CategoryTile label="Stockout risk" value={money(result.summary.stockout_risk_value_sar)} tone="red" />
                <CategoryTile label="Margin leakage" value={money(result.summary.margin_leakage_sar)} tone="green" />
              </div>
            </div>

            <div className="p-6 md:p-8">
              <div className="grid gap-3 sm:grid-cols-3">
                <Kpi label="Inventory value" value={money(result.summary.inventory_value_sar)} tone="gold" />
                <Kpi label="Revenue at risk" value={money(result.summary.revenue_at_risk_sar)} tone="gold" />
                <Kpi
                  label="Potentially recoverable"
                  value={`${money(result.summary.recoverable_value_low_sar)}–${money(result.summary.recoverable_value_high_sar)}`}
                  tone="green"
                />
              </div>

              {result.summary.headline_note && (
                <p className="mt-6 rounded-xl bg-brand-cream/[0.04] p-3 text-xs leading-5 text-brand-cream/50">
                  {result.summary.headline_note}
                </p>
              )}

              <h4 className="mt-8 text-sm font-bold uppercase tracking-wider text-brand-cream/55">Top actions</h4>
              <div className="mt-4 space-y-3">
                {result.actions.slice(0, 3).map((action, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col gap-2 rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.04] p-4 md:flex-row md:items-center md:justify-between"
                  >
                    <div>
                      <p className="font-semibold text-brand-cream">{action.title}</p>
                      <p className="mt-1 text-sm leading-5 text-brand-cream/55">{action.description}</p>
                    </div>
                    <div className="shrink-0 text-left md:text-right" dir="ltr">
                      <p className="text-lg font-black text-brand-green">
                        {action.expected_recovery_sar != null ? money(action.expected_recovery_sar) : "Not estimated"}
                      </p>
                      <p className="text-xs text-brand-cream/45">{action.recovery_confidence || "INSUFFICIENT DATA"}</p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <button
                  onClick={reset}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-brand-cream/10 px-5 py-3 text-sm font-bold text-brand-cream/75 hover:bg-brand-cream/5"
                >
                  <RefreshCw className="h-4 w-4" /> Try another file
                </button>
                <a
                  href="/register?intent=free-audit"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-amber px-5 py-3 text-sm font-bold text-brand-night hover:bg-brand-gold-soft"
                >
                  See My Full Audit {rtl ? <ArrowLeft className="h-4 w-4" /> : <ArrowRight className="h-4 w-4" />}
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
            className="rounded-3xl border border-brand-red/30 bg-brand-red/10 p-8 text-center text-brand-cream"
          >
            <AlertTriangle className="mx-auto mb-4 h-10 w-10 text-brand-red-light" />
            <h3 className="text-lg font-bold">Could not run the free audit</h3>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-brand-cream/65">{error}</p>
            <button
              onClick={reset}
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-amber px-5 py-3 text-sm font-bold text-brand-night hover:bg-brand-gold-soft"
            >
              <RefreshCw className="h-4 w-4" /> Try again
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function FileSlot({
  slot,
  label,
  hint,
  dragging,
  onDragEnter,
  onDrop,
  onChange,
}: {
  slot: "sales" | "inventory";
  label: string;
  hint: string;
  dragging: "sales" | "inventory" | null;
  onDragEnter: (v: "sales" | "inventory" | null) => void;
  onDrop: (e: DragEvent<HTMLLabelElement>) => void;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        onDragEnter(slot);
      }}
      onDragLeave={() => onDragEnter(null)}
      onDrop={onDrop}
      className="block cursor-pointer"
    >
      <div
        className={cn(
          "flex flex-col items-center justify-center rounded-3xl border-2 border-dashed p-7 text-center transition-all",
          dragging === slot
            ? "border-brand-amber bg-brand-amber/10"
            : "border-brand-cream/15 bg-brand-cream/[0.04] hover:border-brand-amber/60 hover:bg-brand-cream/[0.06]"
        )}
      >
        <input type="file" accept={ACCEPT} className="hidden" onChange={onChange} />
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-amber/15">
          {slot === "sales" ? (
            <UploadCloud className="h-6 w-6 text-brand-amber" />
          ) : (
            <FileSpreadsheet className="h-6 w-6 text-brand-amber" />
          )}
        </div>
        <h3 className="text-lg font-bold text-brand-cream">{label}</h3>
        <p className="mt-1 text-xs text-brand-cream/55">{hint}</p>
      </div>
    </label>
  );
}

function CategoryTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "red" | "gold" | "green";
}) {
  const colors = {
    red: "text-brand-red-light",
    gold: "text-brand-amber",
    green: "text-brand-green",
  };
  return (
    <div className="rounded-2xl border border-brand-cream/10 bg-brand-night/20 p-4">
      <p className="text-xs uppercase tracking-wider text-brand-cream/45">{label}</p>
      <p className={cn("mt-1 font-serif text-2xl font-black", colors[tone])}>{value}</p>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: "red" | "gold" | "green" }) {
  const colors = {
    red: "text-brand-red-light",
    gold: "text-brand-amber",
    green: "text-brand-green",
  };
  return (
    <div className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.04] p-4">
      <p className="text-xs uppercase tracking-wider text-brand-cream/45">{label}</p>
      <p className={cn("mt-1 font-serif text-2xl font-black", colors[tone])}>{value}</p>
    </div>
  );
}