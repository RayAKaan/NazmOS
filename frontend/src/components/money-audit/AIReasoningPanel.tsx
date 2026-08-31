"use client";

import { useState } from "react";

type ModeResult = {
  sku?: string;
  deterministic_decision?: string;
  final_decision?: string;
  decision_source?: string;
  ai_confidence?: number;
  ai_reasoning?: string;
  validation?: { reason?: string; is_valid?: boolean; constraint_rejected?: boolean } | null;
};

const SOURCE_LABELS: Record<string, string> = {
  AI_REASONING: "AI override",
  AI_AGREES: "AI agrees",
  DETERMINISTIC_AI_MANUAL_REVIEW: "AI → manual review",
  DETERMINISTIC_LOW_AI_CONFIDENCE: "Deterministic (low AI confidence)",
  DETERMINISTIC_OVERRIDES_LOW_CONFIDENCE_AI: "Deterministic overrode AI",
  DETERMINISTIC: "Deterministic fallback",
  DETERMINISTIC_NO_AI: "Deterministic",
};

export default function AIReasoningPanel({ auditId }: { auditId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<ModeResult[]>([]);
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/money-audit/${auditId}/ab-compare`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      setRows(body.mode_b || []);
      setComparison(body.comparison || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load AI reasoning");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold">How NazmOS Reasons (AI vs Deterministic)</h2>
          <p className="text-sm text-muted-foreground">
            Every ambiguous item, what the deterministic engine decided, what AI concluded,
            and which one was followed.
          </p>
        </div>
        <button
          onClick={() => { setOpen(!open); if (!open && rows.length === 0) load(); }}
          className="rounded-xl border border-brand-amber px-4 py-2 text-sm font-bold text-brand-amber hover:bg-brand-amber/10"
        >
          {open ? "Hide" : loading ? "Loading…" : "Show AI reasoning"}
        </button>
      </div>

      {open && (
        <div className="mt-5 space-y-3">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {comparison != null && (
            <p className="text-xs text-muted-foreground">
              Items evaluated: {String((comparison as Record<string, unknown>).items_evaluated ?? "—")} ·
              {" "}AI overrides: {String((comparison as Record<string, unknown>).ai_overrides ?? 0)} ·
              {" "}AI agrees: {String((comparison as Record<string, unknown>).ai_agreements ?? 0)} ·
              {" "}Constraint rejections: {String((comparison as Record<string, unknown>).constraint_rejections ?? 0)}
              {" "}· SIMULATION — comparison only, nothing executed here.
            </p>
          )}
          {rows.map((r, i) => (
            <details key={`${r.sku}-${i}`} className="rounded-xl border border-border p-4">
              <summary className="cursor-pointer text-sm font-semibold">
                {r.sku} — followed: {SOURCE_LABELS[r.decision_source || ""] || r.decision_source}
                {typeof r.ai_confidence === "number" && r.ai_confidence > 0
                  ? ` · confidence ${(r.ai_confidence * 100).toFixed(0)}%` : ""}
              </summary>
              <div className="mt-2 space-y-1 text-sm">
                <p><span className="text-muted-foreground">Deterministic:</span> {r.deterministic_decision}</p>
                <p><span className="text-muted-foreground">Final:</span> {r.final_decision}</p>
                {r.ai_reasoning && (
                  <p><span className="text-muted-foreground">AI reasoning:</span> {r.ai_reasoning}</p>
                )}
                {r.validation?.reason && (
                  <p className="text-muted-foreground">Validator: {r.validation.reason}</p>
                )}
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
