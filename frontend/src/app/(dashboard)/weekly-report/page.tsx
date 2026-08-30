"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, TrendingUp, AlertTriangle, Clock } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { Card } from "@/components/ui/Card";
import { BentoGrid } from "@/components/ui/BentoGrid";
import { FigureHeadline } from "@/components/ui/FigureHeadline";

/**
 * Weekly Money Report (Phase 3, §17). Observed vs estimated impact are kept
 * strictly separate — estimates are never presented as realized revenue.
 */
interface PriorityItem {
  id: string;
  title: string;
  category: string;
  domain: string;
  severity: string;
  urgency: string;
  estimated_financial_impact_sar: number | null;
  recurring: boolean;
  worsening: boolean;
  goal_aligned: boolean;
  data_quality_score: number | null;
  priority: number;
}

interface WeeklyReport {
  impact: {
    total_sar: number;
    observed_sar: number;
    estimated_sar: number;
    by_type: { impact_type: string; total_sar: number; observed_sar: number }[];
  };
  health: { overall_health: number; dimensions: { dimension: string; score: number; findings: number }[] };
  top_findings: { title: string; severity: string; domain: string; estimated_financial_impact_sar: number }[];
  top_actions_completed: { title: string; action_type: string; status: string }[];
  pending_approvals: number;
  unresolved_issues: number;
  note: string;
  priorities: PriorityItem[];
}

function money(v: number | null | undefined) {
  return (v ?? 0).toLocaleString("en-SA", { maximumFractionDigits: 0 });
}

const typeLabel: Record<string, string> = {
  money_recovered: "Money recovered",
  revenue_protected: "Revenue protected",
  cost_reduced: "Costs reduced",
  margin_recovered: "Margin recovered",
  inventory_released: "Inventory released",
  hours_saved: "Hours saved",
};

export default function WeeklyReportPage() {
  const router = useRouter();
  const { businessId } = useAppStore();
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!businessId) return;
    (async () => {
      try {
        const res = await api.get(`/audits/weekly-report`, { params: { business_id: businessId } });
        setReport(res.data);
      } catch {
        /* leave report null */
      } finally {
        setLoading(false);
      }
    })();
  }, [businessId]);

  if (loading) return <Card density="data" className="animate-pulse"><div className="h-64" /></Card>;

  return (
    <div className="space-y-6">
      <button onClick={() => router.back()} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <header>
        <h1 className="text-2xl font-bold tracking-[-0.03em] md:text-3xl">NazmOS Weekly Report</h1>
        {report?.note && <p className="mt-1 text-xs text-muted-foreground">{report.note}</p>}
      </header>

      {!report ? (
        <Card density="data"><p className="text-muted-foreground">No report data available yet. Run an audit to begin.</p></Card>
      ) : (
        <>
          <BentoGrid cols={{ base: 1, md: 2, lg: 4 }} gap={6}>
            <Card density="editorial" trim="weave" hoverable>
              <span className="text-xs uppercase tracking-[0.04em] text-muted-foreground">Money recovered</span>
              <FigureHeadline value={report.impact.observed_sar} currency="SAR" label="" size="secondary" className="mt-2" />
              <p className="mt-1 text-xs text-muted-foreground">Observed (measured)</p>
            </Card>
            <Card density="editorial" hoverable>
              <span className="text-xs uppercase tracking-[0.04em] text-muted-foreground">Estimated impact</span>
              <FigureHeadline value={report.impact.estimated_sar} currency="SAR" label="" size="secondary" className="mt-2" />
              <p className="mt-1 text-xs text-muted-foreground">Projected, not realized</p>
            </Card>
            <Card density="editorial" hoverable>
              <span className="text-xs uppercase tracking-[0.04em] text-muted-foreground">Pending approvals</span>
              <p className="mt-2 flex items-center gap-2 font-sans text-3xl font-bold tabular-nums text-warning">
                <Clock className="h-5 w-5" /> {report.pending_approvals}
              </p>
            </Card>
            <Card density="editorial" hoverable>
              <span className="text-xs uppercase tracking-[0.04em] text-muted-foreground">Unresolved issues</span>
              <p className="mt-2 flex items-center gap-2 font-sans text-3xl font-bold tabular-nums text-destructive">
                <AlertTriangle className="h-5 w-5" /> {report.unresolved_issues}
              </p>
              <Link href="/dashboard" className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
                Review findings
              </Link>
            </Card>
          </BentoGrid>

          {/* Phase 12 §Part 10: "What should I know this week?" — top priorities. */}
          {report.priorities && report.priorities.length > 0 && (
            <Card density="editorial">
              <h2 className="mb-4 text-lg font-semibold text-foreground">What should I know this week?</h2>
              <ol className="space-y-3">
                {report.priorities.slice(0, 5).map((p, i) => (
                  <li key={p.id} className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                      {i + 1}
                    </span>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-foreground">{p.title}</p>
                        {p.recurring && <span className="rounded-full bg-warning/10 px-2 py-0.5 text-[10px] font-bold uppercase text-warning">recurring</span>}
                        {p.worsening && <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-bold uppercase text-destructive">worsening</span>}
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {p.category.replace(/_/g, " ")}
                        {typeof p.estimated_financial_impact_sar === "number" && <> · SAR {money(p.estimated_financial_impact_sar)}</>}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          <Card density="editorial">
            <h2 className="mb-4 text-lg font-semibold">Impact breakdown</h2>
            <ul className="space-y-2">
              {report.impact.by_type.map((t) => (
                <li key={t.impact_type} className="flex items-center justify-between border-b border-border pb-2 text-sm">
                  <span className="text-muted-foreground">{typeLabel[t.impact_type] ?? t.impact_type}</span>
                  <span className="font-medium tabular-nums text-foreground">
                    SAR {money(t.total_sar)}
                    <span className="ml-2 text-xs text-success">({money(t.observed_sar)} observed)</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card density="editorial">
              <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
                <TrendingUp className="h-5 w-5 text-primary" /> Business health
              </h2>
              <div className="mb-4 flex items-baseline gap-2">
                <span className="font-sans text-4xl font-extrabold tabular-nums tracking-[-0.03em]">{report.health.overall_health}</span>
                <span className="text-muted-foreground">/ 100</span>
              </div>
              <ul className="space-y-1.5">
                {report.health.dimensions.map((d) => (
                  <li key={d.dimension} className="flex items-center justify-between text-sm">
                    <span className="capitalize text-muted-foreground">{d.dimension}</span>
                    <span className="flex items-center gap-3">
                      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                        <span className="block h-full rounded-full bg-primary" style={{ width: `${d.score}%` }} />
                      </span>
                      <span className="w-8 text-right font-medium tabular-nums">{d.score}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card density="editorial">
              <h2 className="mb-4 text-lg font-semibold">Top problems found</h2>
              {report.top_findings.length === 0 ? (
                <p className="text-sm text-muted-foreground">No open findings this week.</p>
              ) : (
                <>
                  <ul className="space-y-2">
                    {report.top_findings.map((f, i) => (
                      <li key={i} className="flex items-start justify-between gap-3 text-sm">
                        <div>
                          <p className="font-medium text-foreground">{f.title}</p>
                          <p className="text-xs text-muted-foreground">{f.domain.replace("_", " ")}</p>
                        </div>
                        <span className="shrink-0 font-medium tabular-nums text-foreground">
                          SAR {money(f.estimated_financial_impact_sar)}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <Link href="/dashboard" className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
                    Review all findings
                  </Link>
                </>
              )}

              <h2 className="mb-3 mt-6 flex items-center gap-2 text-lg font-semibold">
                <CheckCircle2 className="h-5 w-5 text-success" /> Actions completed
              </h2>
              {report.top_actions_completed.length === 0 ? (
                <p className="text-sm text-muted-foreground">No actions completed yet.</p>
              ) : (
                <ul className="space-y-1.5">
                  {report.top_actions_completed.map((a, i) => (
                    <li key={i} className="flex items-center justify-between text-sm">
                      <span className="text-foreground">{a.title}</span>
                      <span className="text-xs capitalize text-muted-foreground">{a.status.replace("_", " ")}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
