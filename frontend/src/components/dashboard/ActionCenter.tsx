"use client";

import Link from "next/link";
import { AlertTriangle, CheckCircle2, Sparkles, ArrowRight, ShieldCheck, Target, TrendingUp, TrendingDown, RefreshCw, Brain, Gauge } from "lucide-react";
import { useActionCenter } from "@/hooks/useActionCenter";
import { Card } from "@/components/ui/Card";
import { BentoGrid } from "@/components/ui/BentoGrid";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import { cn } from "@/lib/utils";

/**
 * Action Center (Phase 2, brief §3) — the Dashboard's evolution from an analytics
 * grid into the place a merchant goes to act. Rendered with the existing v2/v3
 * design system (Card / FigureHeadline / BentoGrid), no second visual language.
 *
 * Sections: Business Health · Money at Risk · Needs Approval · Recent Impact.
 */

const severityTone: Record<string, string> = {
  critical: "text-destructive",
  high: "text-warning",
  medium: "text-secondary",
  low: "text-muted-foreground",
  info: "text-muted-foreground",
};

function money(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString("en-SA", { maximumFractionDigits: 0 });
}

export function ActionCenter() {
  const { report, impact, findings, approvals, goals, healthTrend, comparison, learning, strategies, ops, isLoading } = useActionCenter();

  if (isLoading) {
    return (
      <Card density="data" className="animate-pulse">
        <div className="h-24 rounded-lg bg-muted" />
      </Card>
    );
  }

  const criticalFindings = findings.filter((f) => f.severity === "critical" || f.severity === "high");
  const pendingApprovals = approvals.filter((a) => a.can_approve);

  return (
    <section className="space-y-6">
      {/* Phase 11 §Part 12: simple merchant-facing operational status (no internals). */}
      {ops && ops.status !== "healthy" && (
        <div className={cn(
          "flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm",
          ops.status === "requires_reconciliation" ? "border-destructive/30 bg-destructive/5 text-destructive" : "border-warning/30 bg-warning/5 text-warning"
        )}>
          <span className="h-2 w-2 rounded-full bg-current" />
          <span>{ops.merchant_summary}</span>
        </div>
      )}

      {/* ── Top strip: health / money at risk / actions / approvals ── */}
      <BentoGrid cols={{ base: 1, md: 2, lg: 4 }} gap={6}>
        <Card density="editorial" trim="weave" hoverable>
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-[0.04em] text-muted-foreground">
              Business Health
            </span>
            <ShieldCheck className="h-4 w-4 text-secondary" />
          </div>
          <div className="mt-2 font-serif text-4xl font-extrabold tabular-nums tracking-[-0.03em] text-foreground">
            {report?.overall_health ?? 0}
            <span className="ml-1 text-base font-semibold text-muted-foreground">/ 100</span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {report?.critical ?? 0} critical · {report?.important ?? 0} important · {report?.watch ?? 0} watch
          </p>
        </Card>

        <Card density="editorial" trim="weave" hoverable>
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-[0.04em] text-muted-foreground">
              Capital at Risk
            </span>
            <AlertTriangle className="h-4 w-4 text-destructive" />
          </div>
          <FigureHeadline
            value={report?.capital_at_risk_sar ?? 0}
            currency="SAR"
            label=""
            size="secondary"
            className="mt-2"
          />
        </Card>

        <Card density="editorial" hoverable>
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-[0.04em] text-muted-foreground">
              NazmOS Actions
            </span>
            <Sparkles className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-2 font-serif text-4xl font-extrabold tabular-nums tracking-[-0.03em] text-foreground">
            {approvals.filter((a) => !a.can_approve).length}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Actions completed</p>
        </Card>

        <Card density="editorial" hoverable className={cn(pendingApprovals.length > 0 && "border-border/40")}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-[0.04em] text-muted-foreground">
              Needs Your Approval
            </span>
            <CheckCircle2 className="h-4 w-4 text-warning" />
          </div>
          <div className="mt-2 font-serif text-4xl font-extrabold tabular-nums tracking-[-0.03em] text-warning">
            {pendingApprovals.length}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Approvals required</p>
        </Card>
      </BentoGrid>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── Needs approval ── */}
        <Card density="editorial">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">Needs approval</h2>
            <Link href="/feed" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
              View all <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          {pendingApprovals.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing waiting for you. 🎉</p>
          ) : (
            <ul className="space-y-3">
              {pendingApprovals.slice(0, 5).map((a) => (
                <li key={a.id} className="rounded-lg border border-border bg-card p-3 shadow-elevation-1">
                  <p className="text-sm font-semibold text-foreground">{a.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{a.summary}</p>
                  {typeof a.estimated_value_sar === "number" && (
                    <p className="mt-1 text-xs font-medium text-primary">SAR {money(a.estimated_value_sar)}</p>
                  )}
                  <div className="mt-2 flex gap-2">
                    <Link href={`/feed?approve=${a.id}`} className="rounded-md bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:bg-primary/90">
                      Approve
                    </Link>
                    <Link href={`/feed?reject=${a.id}`} className="rounded-md border border-border px-3 py-1.5 text-xs font-bold text-muted-foreground hover:bg-muted">
                      Reject
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* ── Top findings + impact ── */}
        <Card density="editorial">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">What needs attention</h2>
            <span className="text-xs text-muted-foreground">
              {criticalFindings.length} high-priority finding{criticalFindings.length === 1 ? "" : "s"}
            </span>
          </div>
          {criticalFindings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No high-priority findings.</p>
          ) : (
            <ul className="space-y-3">
              {criticalFindings.slice(0, 5).map((f) => (
                <li key={f.id}>
                  <Link href={`/findings/${f.id}`} className="block rounded-lg border border-border p-3 shadow-elevation-1 transition-colors hover:bg-surface-hover">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{f.title}</p>
                        <p className="mt-0.5 text-xs capitalize text-muted-foreground">{f.domain.replace("_", " ")} · {f.category.replace("_", " ")}</p>
                      </div>
                      <span className={cn("text-xs font-bold uppercase", severityTone[f.severity] ?? "text-muted-foreground")}>
                        {f.severity}
                      </span>
                    </div>
                    {typeof f.estimated_financial_impact_sar === "number" && (
                      <p className="mt-1 text-xs font-medium text-primary">SAR {money(f.estimated_financial_impact_sar)}</p>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-6 border-t border-border pt-4">
            <h3 className="mb-2 text-sm font-medium uppercase tracking-wider text-muted-foreground">Impact</h3>
            <div className="flex items-baseline gap-2">
              <span className="font-sans text-3xl font-bold tabular-nums tracking-[-0.03em] text-success">
                SAR {money(impact?.total_sar ?? report?.impact?.total_sar ?? 0)}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {money(impact?.observed_sar ?? report?.impact?.observed_sar ?? 0)} verified ·{" "}
              {money(impact?.estimated_sar ?? report?.impact?.estimated_sar ?? 0)} estimated
            </p>
          </div>
        </Card>
      </div>

      {/* ── This week: audit comparison (§15) + what NazmOS learned (§13) ── */}
      {(comparison || learning) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {comparison && (
            <Card density="editorial">
              <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-foreground">
                <RefreshCw className="h-5 w-5 text-secondary" /> This week
              </h2>
              <div className="flex flex-wrap gap-2 text-sm">
                {comparison.counts.new > 0 && <span className="rounded-full bg-secondary/10 px-2.5 py-1 font-medium text-secondary">+{comparison.counts.new} new</span>}
                {comparison.counts.improving > 0 && <span className="rounded-full bg-success/10 px-2.5 py-1 font-medium text-success">↓{comparison.counts.improving} improving</span>}
                {comparison.counts.worsening > 0 && <span className="rounded-full bg-destructive/10 px-2.5 py-1 font-medium text-destructive">↑{comparison.counts.worsening} worsening</span>}
                {comparison.counts.resolved > 0 && <span className="rounded-full bg-success/10 px-2.5 py-1 font-medium text-success">✓{comparison.counts.resolved} resolved</span>}
                {comparison.counts.recurring > 0 && <span className="rounded-full bg-warning/10 px-2.5 py-1 font-medium text-warning">↻{comparison.counts.recurring} recurring</span>}
                {comparison.counts.persistent > 0 && <span className="rounded-full bg-muted px-2.5 py-1 font-medium text-muted-foreground">{comparison.counts.persistent} persistent</span>}
              </div>
              {comparison.findings.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {comparison.findings.slice(0, 4).map((f) => (
                    <li key={f.id}>
                      <Link href={`/findings/${f.id}`} className="flex items-center justify-between gap-2 text-sm text-muted-foreground hover:text-foreground">
                        <span className="truncate">{f.title}</span>
                        <span className={cn("shrink-0 text-xs font-bold uppercase",
                          f.status === "improving" || f.status === "resolved" ? "text-success" :
                          f.status === "worsening" ? "text-destructive" :
                          f.status === "recurring" ? "text-warning" : "text-secondary")}>
                          {f.status}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}

          {learning && (learning.attempts > 0) && (
            <Card density="editorial">
              <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-foreground">
                <Brain className="h-5 w-5 text-primary" /> What NazmOS learned
              </h2>
              <p className="text-sm text-muted-foreground">
                {learning.attempts} intervention{learning.attempts === 1 ? "" : "s"} · {learning.succeeded} succeeded · {learning.rejected} rejected
              </p>
              {typeof learning.success_rate === "number" && (
                <p className="mt-1 text-sm">
                  Verified success rate: <span className="font-semibold text-foreground">{(learning.success_rate * 100).toFixed(0)}%</span>
                </p>
              )}
              {typeof learning.effectiveness === "number" && (
                <p className="mt-1 text-sm">
                  Effectiveness (actual/expected): <span className={cn("font-semibold", learning.effectiveness >= 0.8 ? "text-success" : learning.effectiveness >= 0.5 ? "text-warning" : "text-destructive")}>
                    {(learning.effectiveness * 100).toFixed(0)}%
                  </span>
                </p>
              )}
              {learning.total_actual_impact_sar > 0 && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Observed value from interventions: <span className="font-semibold text-success">SAR {money(learning.total_actual_impact_sar)}</span>
                </p>
              )}
            </Card>
          )}
        </div>
      )}

      {/* ── Strategy performance (§20): minimal, evidence-tiered ── */}
      {strategies.length > 0 && (
        <Card density="editorial">
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-foreground">
            <Gauge className="h-5 w-5 text-primary" /> Strategy performance
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="pb-2 pr-4">Strategy</th>
                  <th className="pb-2 pr-4">Success</th>
                  <th className="pb-2 pr-4">Effectiveness</th>
                  <th className="pb-2">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {strategies.slice(0, 5).map((s) => (
                  <tr key={s.action_type} className="border-t border-border">
                    <td className="py-2 pr-4 font-medium text-foreground">{s.action_type.replace(/_/g, " ")}</td>
                    <td className="py-2 pr-4 tabular-nums">{typeof s.success_rate === "number" ? `${(s.success_rate * 100).toFixed(0)}%` : "—"}</td>
                    <td className="py-2 pr-4 tabular-nums">{typeof s.effectiveness === "number" ? `${(s.effectiveness * 100).toFixed(0)}%` : "—"}</td>
                    <td className={cn("py-2 text-xs font-medium",
                      s.evidence_tier === "strong" ? "text-success" : s.evidence_tier === "preliminary" ? "text-warning" : "text-muted-foreground")}>
                      {s.evidence_tier}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Based on historical interventions. Strategies never bypass approval policy.
          </p>
        </Card>
      )}

      {/* ── Goals + health trend (§2–4, §24) ── */}
      {(goals.length > 0 || healthTrend) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {goals.length > 0 && (
            <Card density="editorial">
              <div className="mb-4 flex items-center gap-2">
                <Target className="h-5 w-5 text-primary" />
                <h2 className="text-lg font-semibold text-foreground">Business goals</h2>
              </div>
              <ul className="space-y-3">
                {goals.slice(0, 4).map((g) => (
                  <li key={g.id} className="rounded-lg border border-border p-3 shadow-elevation-1">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-foreground">{g.title}</p>
                      <span className={cn(
                        "text-xs font-bold uppercase",
                        g.trajectory === "achieved" ? "text-success" : g.trajectory === "on_track" ? "text-secondary" : "text-warning"
                      )}>
                        {g.trajectory?.replace("_", " ")}
                      </span>
                    </div>
                    {typeof g.progress_pct === "number" && (
                      <div className="mt-2 flex items-center gap-2">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, g.progress_pct)}%` }} />
                        </div>
                        <span className="w-12 text-right text-xs font-medium tabular-nums">{g.progress_pct}%</span>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {healthTrend && (
            <Card density="editorial">
              <div className="mb-4 flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-secondary" />
                <h2 className="text-lg font-semibold text-foreground">Health trend</h2>
              </div>
              <div className="flex items-baseline gap-3">
                <span className="font-serif text-4xl font-extrabold tabular-nums tracking-[-0.03em] text-foreground">
                  {healthTrend.current_health}
                </span>
                <span className="flex items-center gap-1 text-sm font-medium">
                  {healthTrend.trend === "up" ? (
                    <TrendingUp className="h-4 w-4 text-success" />
                  ) : healthTrend.trend === "down" ? (
                    <TrendingDown className="h-4 w-4 text-destructive" />
                  ) : null}
                  <span className={cn(
                    healthTrend.trend === "up" ? "text-success" : healthTrend.trend === "down" ? "text-destructive" : "text-muted-foreground"
                  )}>
                    {healthTrend.delta > 0 ? "+" : ""}{healthTrend.delta}
                  </span>
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Previous period: {healthTrend.previous_health} · {healthTrend.note}
              </p>
            </Card>
          )}
        </div>
      )}
    </section>
  );
}
