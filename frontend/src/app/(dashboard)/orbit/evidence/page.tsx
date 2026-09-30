"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { EvidenceViewer } from "@/components/orbit/EvidenceViewer";
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

export default function OrbitEvidencePage() {
  const pathname = usePathname();
  const { selectedAuditId, setSelectedAuditId } = useOrbitStore();

  useEffect(() => {
    const auditId = new URLSearchParams(window.location.search).get("audit_id");
    if (auditId) setSelectedAuditId(auditId);
  }, [setSelectedAuditId]);

  const historyQuery = useQuery<{ audits?: any[] }>({
    queryKey: ["orbit-history"],
    queryFn: async () => {
      const res = await fetch("/api/v1/orbit/audits");
      return res.json();
    },
  });

  const auditQuery = useQuery<any>({
    queryKey: ["orbit-audit", selectedAuditId],
    queryFn: async () => {
      if (!selectedAuditId) return null;
      const res = await fetch(`/api/v1/orbit/audits/${selectedAuditId}`);
      return res.json();
    },
    enabled: !!selectedAuditId,
  });

  const audits = historyQuery.data?.audits ?? [];
  const audit = auditQuery.data;

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
    historyQuery.isLoading ? (
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
            <h1 className="text-2xl md:text-3xl font-bold">Orbit Evidence</h1>
            <p className="text-muted-foreground">Select an audit from the history to view its evidence registry</p>
          </div>
        </div>

        {renderTabs()}

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

  const evidence = audit.evidence || {};

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => setSelectedAuditId(null)} className="p-2 hover:bg-brand-cream/5 rounded-lg transition-colors mb-2 inline-block" aria-label="Back to history">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="text-2xl md:text-3xl font-bold">Orbit Evidence</h1>
          <p className="text-muted-foreground">{Object.keys(evidence).length} evidence records · {format(new Date(), "PPP p")}</p>
        </div>
      </div>

      <EvidenceViewer evidence={evidence} isLoading={auditQuery.isLoading} />
    </div>
  );
}