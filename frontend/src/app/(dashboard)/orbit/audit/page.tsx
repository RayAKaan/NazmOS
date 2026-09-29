"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { TopOpportunities } from "@/components/orbit/TopOpportunities";
import { DataQualityPanel } from "@/components/orbit/DataQualityPanel";
import { AuditComparison } from "@/components/orbit/AuditComparison";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { useOrbitStore } from "@/stores/orbitStore";

const ORBIT_TABS = [
  { href: "/orbit", label: "Overview" },
  { href: "/orbit/audit", label: "Audit" },
  { href: "/orbit/data", label: "Data" },
  { href: "/orbit/evidence", label: "Evidence" },
  { href: "/orbit/findings", label: "Findings" },
];

function scoreBadge(score: number) {
  return cn(
    "px-2 py-1 rounded-full text-xs font-bold",
    score >= 70
      ? "bg-accent-green/10 text-accent-green"
      : score >= 50
        ? "bg-accent-yellow/10 text-accent-yellow"
        : "bg-accent-red/10 text-accent-red"
  );
}

interface OrbitAudit {
  audit_id: string;
  business_id: string;
  business_type: string;
  period: { start: string; end: string };
  health_score: number;
  health_breakdown: any;
  exposures: any;
  findings: any[];
  opportunities: any[];
  evidence: any;
  limitations: any;
  sources: any[];
  generated_at: string;
  metrics: Record<string, any>;
}

export default function OrbitAuditPage() {
  const pathname = usePathname();
  const { selectedAuditId, setSelectedAuditId } = useOrbitStore();
  const [showComparison, setShowComparison] = useState(false);

  useEffect(() => {
    const auditId = new URLSearchParams(window.location.search).get("audit_id");
    if (auditId) setSelectedAuditId(auditId);
  }, [setSelectedAuditId]);

  const { data: history, isLoading: historyLoading } = useQuery<{ audits?: any[] }>({
    queryKey: ["orbit-history"],
    queryFn: async () => {
      const res = await fetch("/api/v1/orbit/audits");
      return res.json();
    },
  });

  const { data: audit, isLoading: auditLoading } = useQuery<OrbitAudit | null>({
    queryKey: ["orbit-audit", selectedAuditId],
    queryFn: async () => {
      if (!selectedAuditId) return null;
      const res = await fetch(`/api/v1/orbit/audits/${selectedAuditId}`);
      return res.json();
    },
    enabled: !!selectedAuditId,
  });

  const comparisonQuery = useQuery<any>({
    queryKey: ["orbit-comparison", selectedAuditId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/orbit/audits/${selectedAuditId}/compare`);
      if (!res.ok) throw new Error("Comparison unavailable");
      return res.json();
    },
    enabled: !!selectedAuditId && showComparison,
  });

  const audits = history?.audits ?? [];

  const renderTabs = () => (
    <div className="flex flex-wrap gap-2">
      {ORBIT_TABS.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={cn(
            "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
            pathname === tab.href ? "bg-accent-yellow/20 text-accent-yellow" : "text-muted-foreground hover:bg-brand-cream/5"
          )}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );

  const renderHistoryRows = (keyPrefix: string) =>
    historyLoading ? (
      <tr key={`${keyPrefix}-loading`}>
        <td colSpan={4} className="py-8">
          <div className="h-4 w-full bg-brand-cream/5 rounded animate-pulse" />
        </td>
      </tr>
    ) : audits.length === 0 ? (
      <tr key={`${keyPrefix}-empty`}>
        <td colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
          No audits yet.{" "}
          <Link href="/upload" className="text-brand-amber font-medium hover:underline">
            Upload files to run your first audit
          </Link>
        </td>
      </tr>
    ) : (
      audits.map((item: any) => {
        const score = item.health_score ?? 0;
        const period = item.period_start ? `${String(item.period_start).slice(0, 10)} → ${String(item.period_end ?? "").slice(0, 10)}` : "—";
        return (
          <tr key={`${keyPrefix}-${item.id}`} className="hover:bg-brand-cream/5">
            <td className="py-4 text-sm text-brand-cream/60">{format(new Date(item.created_at), "PPP")}</td>
            <td className="py-4">
              <span className={scoreBadge(score)}>{score}/100</span>
            </td>
            <td className="py-4 text-sm text-brand-cream/60">{period}</td>
            <td className="py-4 text-right">
              <button onClick={() => setSelectedAuditId(item.id)} className="px-3 py-1 text-sm font-medium text-brand-amber hover:bg-brand-amber/10 rounded-lg transition-colors">
                View
              </button>
            </td>
          </tr>
        );
      })
    );

  if (!selectedAuditId) {
    return (
      <div className="space-y-6 animate-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">Orbit Audit</h1>
            <p className="text-muted-foreground">Select an audit from the history or run a new one</p>
          </div>
        </div>

        {renderTabs()}

        <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
            Audit History
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-muted-foreground border-b border-brand-cream/10">
                  <th className="pb-3 font-medium">Date</th>
                  <th className="pb-3 font-medium">Health</th>
                  <th className="pb-3 font-medium">Period</th>
                  <th className="pb-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-cream/5">{renderHistoryRows("list")}</tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  if (!audit) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-1/2 bg-brand-cream/5 rounded animate-pulse" />
      </div>
    );
  }

  const findings = audit.findings || [];
  const opportunities = audit.opportunities || [];

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => setSelectedAuditId(null)} className="p-2 hover:bg-brand-cream/5 rounded-lg transition-colors mb-2 inline-block" aria-label="Back to history">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="text-2xl md:text-3xl font-bold">Orbit Audit</h1>
          <p className="text-muted-foreground">
            {format(new Date(audit.generated_at), "PPP p")} · Health: {audit.health_score}/100
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowComparison((prev) => !prev)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
              showComparison ? "bg-accent-yellow/20 text-accent-yellow" : "text-muted-foreground hover:bg-brand-cream/5"
            )}
          >
            Compare
          </button>
          <button className="p-2 hover:bg-brand-cream/5 rounded-lg transition-colors" aria-label="Refresh" onClick={() => window.location.reload()}>
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 00-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      {renderTabs()}

      {showComparison && (
        <AuditComparison
          comparison={comparisonQuery.data ?? null}
          isLoading={comparisonQuery.isLoading}
        />
      )}

      <div className="grid gap-6 md:grid-cols-3 lg:grid-cols-4">
        <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1 md:col-span-2 lg:col-span-2">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">Business Health</h3>
          <div className="flex items-center justify-center">
            <div className="relative">
              <svg className="w-32 h-32 -rotate-90" aria-hidden="true">
                <circle cx="64" cy="64" r="45" strokeWidth="10" stroke="var(--chart-grid)" fill="none" />
                <circle
                  cx="64"
                  cy="64"
                  r="45"
                  strokeWidth="10"
                  stroke="currentColor"
                  strokeDasharray={2 * Math.PI * 45}
                  strokeDashoffset={2 * Math.PI * 45 * (1 - (audit.health_score || 0) / 100)}
                  strokeLinecap="round"
                  fill="none"
                  className={`transition-all duration-1000 ${audit.health_score >= 70 ? "text-accent-green" : audit.health_score >= 50 ? "text-accent-yellow" : "text-accent-red"}`}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-3xl font-bold text-foreground">{audit.health_score}</span>
              </div>
            </div>
          </div>
          <div className="mt-4 flex justify-center">
            <span className="px-3 py-1 rounded-full text-sm font-medium bg-accent-green/10 border-accent-green/30 text-accent-green">
              {audit.health_score >= 70 ? "Excellent" : audit.health_score >= 50 ? "Needs Attention" : "Critical"}
            </span>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">Capital Exposed</h3>
            <div className="text-3xl font-bold text-foreground">﷼ {audit.exposures?.capital_exposed_sar?.value?.toLocaleString()}</div>
            <p className="text-sm text-muted-foreground mt-1">Capital currently exposed</p>
          </div>
          <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">Revenue at Risk</h3>
            <div className="text-3xl font-bold text-foreground">﷼ {audit.exposures?.revenue_at_risk_sar?.value?.toLocaleString()}</div>
            <p className="text-sm text-muted-foreground mt-1">Revenue potentially at risk</p>
          </div>
          <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">Gross Profit at Risk</h3>
            <div className="text-3xl font-bold text-foreground">﷼ {audit.exposures?.gross_profit_at_risk_sar?.value?.toLocaleString()}</div>
            <p className="text-sm text-muted-foreground mt-1">Gross profit potentially exposed</p>
          </div>
          <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">Estimated Recoverable</h3>
            <div className="text-3xl font-bold text-foreground">﷼ {audit.exposures?.recoverable_range_sar?.low?.value?.toLocaleString()} – {audit.exposures?.recoverable_range_sar?.high?.value?.toLocaleString()}</div>
            <p className="text-sm text-muted-foreground mt-1">Estimated recovery range</p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <TopOpportunities opportunities={audit.opportunities || []} isLoading={false} />
        <DataQualityPanel dataQuality={audit.limitations} isLoading={false} />
        <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">Limitations</h3>
          <ul className="space-y-2 text-sm text-brand-cream/80">
            {audit.limitations?.we_know?.map((item: string, i: number) => (
              <li key={i} className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-accent-green/20 text-accent-green text-xs font-bold">✓</span>
                <span>We know: {item}</span>
              </li>
            ))}
            {audit.limitations?.we_estimate?.map((item: string, i: number) => (
              <li key={`est-${i}`} className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-accent-yellow/20 text-accent-yellow text-xs font-bold">≈</span>
                <span>We estimate: {item}</span>
              </li>
            ))}
            {audit.limitations?.we_dont_know?.map((item: string, i: number) => (
              <li key={`unk-${i}`} className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-accent-red/20 text-accent-red text-xs font-bold">?</span>
                <span>We don't know: {item}</span>
              </li>
            ))}
            {audit.limitations?.upload_next?.map((item: string, i: number) => (
              <li key={`next-${i}`} className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brand-amber/20 text-brand-amber text-xs font-bold">→</span>
                <span>Upload next: {item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="border-t border-brand-cream/10 pt-6">
        <h2 className="text-xl font-bold mb-4">Audit History</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-muted-foreground border-b border-brand-cream/10">
                <th className="pb-3 font-medium">Date</th>
                <th className="pb-3 font-medium">Health</th>
                <th className="pb-3 font-medium">Period</th>
                <th className="pb-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-cream/5">{renderHistoryRows("detail")}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}