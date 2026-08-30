"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, TrendingUp, ArrowRight } from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";

/**
 * Mobile Action Center (Phase 3, §16) — the quick-decision surface for the PWA.
 * Priorities: money at risk, recent impact, critical findings. Not a shrunken
 * desktop dashboard — a compact "what needs my attention" strip.
 */
interface Report {
  overall_health: number;
  capital_at_risk_sar?: number;
  money_at_risk_sar?: number;
  critical: number;
  important: number;
}
interface Impact {
  total_sar: number;
  observed_sar: number;
  estimated_sar: number;
}
interface Finding {
  id: string;
  title: string;
  severity: string;
  estimated_financial_impact_sar: number | null;
}

function money(v: number | null | undefined) {
  return `﷼ ${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

const severityTone: Record<string, string> = {
  critical: "text-destructive",
  high: "text-warning",
  medium: "text-secondary",
};

export function MobileActionCenter() {
  const { businessId } = useAppStore();
  const [report, setReport] = useState<Report | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);

  useEffect(() => {
    if (!businessId) return;
    (async () => {
      try {
        const [r, i, f] = await Promise.allSettled([
          api.get(`/audits/report`, { params: { business_id: businessId } }),
          api.get(`/audits/impact`, { params: { business_id: businessId } }),
          api.get(`/audits/findings`, { params: { business_id: businessId, limit: 5 } }),
        ]);
        if (r.status === "fulfilled") setReport(r.value.data);
        if (i.status === "fulfilled") setImpact(i.value.data);
        if (f.status === "fulfilled") setFindings(f.value.data.findings || []);
      } catch {
        /* degrade gracefully */
      }
    })();
  }, [businessId]);

  const critical = findings.filter((f) => f.severity === "critical" || f.severity === "high");

  if (!report && !impact && critical.length === 0) return null;

  return (
    <section className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-bold flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-primary" /> Action Center
        </h2>
        <Link href="/dashboard" className="flex items-center gap-1 text-xs text-primary">
          Full view <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-3">
          <p className="flex items-center gap-1 text-[11px] uppercase tracking-wider text-muted-foreground">
            <AlertTriangle className="w-3 h-3 text-destructive" /> Money at risk
          </p>
          <p className="mt-1 text-lg font-bold tabular-nums">{money(report?.capital_at_risk_sar ?? 0)}</p>
        </div>
        <div className="rounded-xl border border-success/20 bg-success/5 p-3">
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Impact</p>
          <p className="mt-1 text-lg font-bold tabular-nums text-success">{money(impact?.total_sar)}</p>
          <p className="text-[10px] text-muted-foreground">{money(impact?.observed_sar)} verified</p>
        </div>
      </div>

      {critical.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Critical findings ({critical.length})
          </p>
          {critical.slice(0, 3).map((f) => (
            <Link
              key={f.id}
              href={`/findings/${f.id}`}
              className="flex items-center justify-between gap-2 rounded-xl border border-brand-cream/5 bg-brand-cream/[0.02] p-3"
            >
              <span className="text-sm font-medium line-clamp-1">{f.title}</span>
              <span className={cn("text-[10px] font-bold uppercase", severityTone[f.severity] ?? "text-muted-foreground")}>
                {f.severity}
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
