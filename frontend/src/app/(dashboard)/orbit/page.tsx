"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { HealthScoreCard } from "@/components/orbit/HealthScoreCard";
import { ExposureCards } from "@/components/orbit/ExposureCards";
import { TopOpportunities } from "@/components/orbit/TopOpportunities";
import { DataQualityPanel } from "@/components/orbit/DataQualityPanel";
import { Skeleton } from "@/components/ui/Skeleton";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { RefreshCw, Download, Upload, ChevronLeft as ChevronLeftIcon } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { useOrbitStore } from "@/stores/orbitStore";

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

export default function OrbitOverviewPage() {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { selectedAuditId, setSelectedAuditId } = useOrbitStore();

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

  const audits = history?.audits ?? [];

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
          <button onClick={() => router.push("/upload")} className="text-brand-amber font-medium hover:underline">
            Upload files to run your first audit
          </button>
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

  if (!selectedAuditId) {
    return (
      <div className="space-y-6 animate-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">Orbit</h1>
            <p className="text-muted-foreground">Your Business X-Ray history</p>
          </div>
          <Button variant="outline" className="gap-2" onClick={() => router.push("/upload")}>
            <Upload className="h-4 w-4" />
            New Audit
          </Button>
        </div>

        {renderTabs()}

        <Card className="overflow-hidden">
          <div className="border-b border-brand-cream/10 px-6 py-4">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Audit History
            </h3>
          </div>
          <div className="p-6">
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
        </Card>
      </div>
    );
  }

  if (!audit) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-1/2" />
      </div>
    );
  }

  const findings = audit.findings || [];

  const exportAudit = () => {
    const blob = new Blob([JSON.stringify(audit, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `orbit-audit-${audit.audit_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <button onClick={() => setSelectedAuditId(null)} className="p-2 hover:bg-brand-cream/5 rounded-lg transition-colors" aria-label="Back to history">
              <ChevronLeftIcon className="h-5 w-5" />
            </button>
            <h1 className="text-2xl md:text-3xl font-bold">Orbit</h1>
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-brand-amber/20 text-brand-amber">
              {audit.business_type?.toUpperCase() || "RETAIL"}
            </span>
          </div>
          <p className="text-muted-foreground">
            {format(new Date(audit.generated_at), "PPP p")} · Health: {audit.health_score}/100
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["orbit-history"] });
              queryClient.invalidateQueries({ queryKey: ["orbit-audit"] });
            }}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button variant="outline" onClick={exportAudit}>
            <Download className="h-4 w-4" />
            Export
          </Button>
        </div>
      </div>

      {renderTabs()}

      <div className="grid gap-6 md:grid-cols-3 lg:grid-cols-4">
        <HealthScoreCard score={audit.health_score} isLoading={false} breakdown={audit.health_breakdown} />
        <ExposureCards exposures={audit.exposures} isLoading={false} />
        <div className="md:col-span-2 lg:col-span-3">
          <TopOpportunities opportunities={audit.opportunities} isLoading={false} />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Money Exposure</h2>
      </div>
      <ExposureCards exposures={audit.exposures} isLoading={false} />

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold">Top Opportunities</h2>
      </div>
      <TopOpportunities opportunities={audit.opportunities || []} isLoading={false} />

      <div className="grid gap-6 md:grid-cols-2">
        <DataQualityPanel dataQuality={audit.limitations} isLoading={false} />
        <div className="bg-surface rounded-lg border border-border p-6 shadow-elevation-1">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
            Limitations
          </h3>
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
                <span>We don&apos;t know: {item}</span>
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