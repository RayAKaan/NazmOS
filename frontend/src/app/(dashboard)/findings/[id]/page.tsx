"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, AlertTriangle, CheckCircle2, Clock, ShieldCheck } from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { Card } from "@/components/ui/Card";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import { cn } from "@/lib/utils";

/**
 * Finding detail (Phase 2, brief §20) — the product's trust layer.
 * Problem → Evidence → Impact → Reasoning → Recommended action → Approval →
 * Execution → Verification → Impact.
 */
interface TimelineEvent {
  step: string;
  label: string;
  at?: string;
  rejection_reason?: string;
  actual_impact_sar?: number;
}

interface FindingDetail {
  id: string;
  domain: string;
  category: string;
  severity: string;
  status: string;
  title: string;
  problem: string;
  explanation: string;
  evidence: Record<string, any>;
  affected_entities: { type: string; id?: string; name?: string }[];
  estimated_financial_impact_sar: number | null;
  confidence: number | null;
  recommended_action: Record<string, any>;
  action_risk: string;
  source: string;
  action_status?: string;
  action_outcome?: Record<string, any>;
  executed_at?: string;
  verification_result?: Record<string, any>;
  observed_impact_sar?: number;
  created_at?: string;
  resolved_at?: string;
}

const severityTone: Record<string, string> = {
  critical: "text-destructive",
  high: "text-warning",
  medium: "text-secondary",
  low: "text-muted-foreground",
};

function money(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString("en-SA", { maximumFractionDigits: 0 });
}

export default function FindingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { businessId } = useAppStore();
  const id = params?.id as string;
  const [finding, setFinding] = useState<FindingDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [recommendation, setRecommendation] = useState<any | null>(null);
  const [rootCause, setRootCause] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId || !id) return;
    setLoading(true);
    setError(null);
    try {
      const [detailRes, timelineRes, recRes, rcRes] = await Promise.allSettled([
        api.get(`/audits/findings/${id}`, { params: { business_id: businessId } }),
        api.get(`/audits/findings/${id}/timeline`, { params: { business_id: businessId } }),
        api.get(`/audits/findings/${id}/recommendation`, { params: { business_id: businessId } }),
        api.get(`/audits/findings/${id}/root-cause`, { params: { business_id: businessId } }),
      ]);
      if (detailRes.status === "fulfilled") setFinding(detailRes.value.data);
      else setError(detailRes.reason?.response?.data?.detail || "Could not load finding");
      if (timelineRes.status === "fulfilled") setTimeline(timelineRes.value.data.timeline || []);
      if (recRes.status === "fulfilled") setRecommendation(recRes.value.data);
      if (rcRes.status === "fulfilled") setRootCause(rcRes.value.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Could not load finding");
    } finally {
      setLoading(false);
    }
  }, [businessId, id]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <Card density="data" className="animate-pulse"><div className="h-64" /></Card>;
  if (error || !finding) {
    return (
      <div className="space-y-4">
        <button onClick={() => router.back()} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <p className="text-muted-foreground">{error || "Finding not found"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button onClick={() => router.back()} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </button>

      <header>
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn("text-xs font-bold uppercase tracking-wider", severityTone[finding.severity] ?? "text-muted-foreground")}>
            {finding.severity}
          </span>
          <span className="text-xs uppercase tracking-wider text-muted-foreground">
            {finding.domain.replace("_", " ")} · {finding.category.replace("_", " ")}
          </span>
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
            {finding.status.replace("_", " ")}
          </span>
        </div>
        <h1 className="mt-3 text-2xl font-bold tracking-[-0.03em] text-foreground md:text-3xl">{finding.problem}</h1>
      </header>

      <Card density="editorial" trim="weave">
        <FigureHeadline
          value={finding.estimated_financial_impact_sar ?? 0}
          currency="SAR"
          label="Estimated financial impact"
          size="secondary"
        />
        <p className="mt-2 text-xs text-muted-foreground">
          Confidence {(finding.confidence ?? 0) * 100}% · Risk {finding.action_risk ?? "low"}
        </p>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card density="editorial">
          <h2 className="mb-3 text-lg font-semibold text-foreground">What&apos;s wrong</h2>
          <p className="text-sm leading-6 text-muted-foreground">{finding.explanation || "No explanation recorded."}</p>

          {Object.keys(finding.evidence || {}).length > 0 && (
            <>
              <h3 className="mt-6 mb-2 text-sm font-medium uppercase tracking-wider text-muted-foreground">Evidence</h3>
              <ul className="space-y-1 text-sm text-muted-foreground">
                {Object.entries(finding.evidence).map(([k, v]) => (
                  <li key={k} className="flex gap-2">
                    <span className="font-medium text-foreground">{k}:</span>
                    <span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card density="editorial">
          <h2 className="mb-3 text-lg font-semibold text-foreground">Recommended action</h2>
          <p className="text-sm font-medium text-foreground">
            {(finding.recommended_action || {}).type || "review"}
          </p>
          {finding.recommended_action?.why && (
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{finding.recommended_action.why}</p>
          )}

          <h3 className="mt-6 mb-2 text-sm font-medium uppercase tracking-wider text-muted-foreground">Approval</h3>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <ShieldCheck className="h-4 w-4 text-secondary" />
            {finding.action_risk === "high" ? "Mandatory human approval" : finding.action_risk === "medium" ? "Owner approval required" : "May execute automatically within policy"}
          </p>
        </Card>
      </div>

      <Card density="editorial">
        <h2 className="mb-3 text-lg font-semibold text-foreground">Execution & verification</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex items-start gap-2">
            <Clock className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Execution</p>
              <p className="mt-1 text-sm text-foreground">{finding.action_status ? finding.action_status.replace("_", " ") : "Not yet executed"}</p>
              {finding.executed_at && <p className="text-xs text-muted-foreground">{new Date(finding.executed_at).toLocaleString()}</p>}
            </div>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="mt-0.5 h-4 w-4 text-success" />
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Verification</p>
              <p className="mt-1 text-sm text-foreground">
                {finding.verification_result?.verified ? "Verified" : "Pending"}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 text-primary" />
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Actual impact</p>
              <p className="mt-1 text-sm font-semibold text-success">
                SAR {money(finding.observed_impact_sar ?? finding.verification_result?.actual_impact_sar)}
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* Phase 11 §Part 13: "Why it is happening" — evidence-based root cause. */}
      {rootCause && (
        <Card density="editorial">
          <h2 className="mb-3 text-lg font-semibold text-foreground">Why it is happening</h2>
          {rootCause.status === "uncertain" ? (
            <p className="text-sm text-muted-foreground">
              Root cause uncertain — not enough data yet.
            </p>
          ) : (
            <ul className="space-y-3">
              {(rootCause.hypotheses || []).map((h: any, i: number) => (
                <li key={i} className="rounded-lg border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-foreground">{h.hypothesis}</p>
                    <span className={cn(
                      "shrink-0 rounded-full px-2 py-0.5 text-xs font-bold",
                      h.confidence === "supported" ? "bg-success/10 text-success" :
                      h.confidence === "plausible" ? "bg-warning/10 text-warning" :
                      "bg-muted text-muted-foreground"
                    )}>
                      {h.confidence.replace(/_/g, " ")}
                    </span>
                  </div>
                  {(h.evidence || []).length > 0 && (
                    <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                      {h.evidence.map((e: string, j: number) => <li key={j}>• {e}</li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* Phase 9 §15: "Why this strategy?" — structured, evidence-based, never chain-of-thought. */}
      {recommendation && (
        <Card density="editorial">
          <h2 className="mb-3 text-lg font-semibold text-foreground">Why NazmOS recommends this</h2>
          <div className="mb-4 rounded-lg border border-border/30 bg-primary/5 p-3">
            <p className="text-sm font-semibold text-foreground">
              Recommended: {recommendation.recommended?.replace(/_/g, " ")}
            </p>
          </div>
          <div className="grid gap-3 text-sm md:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Expected impact</p>
              <p className="font-medium">{recommendation.score?.explanation?.impact_label ?? "n/a"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Urgency</p>
              <p className="font-medium capitalize">{recommendation.score?.explanation?.urgency ?? "medium"}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Confidence</p>
              <p className="font-medium">{recommendation.score?.explanation?.confidence}%</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Data quality</p>
              <p className="font-medium">{recommendation.score?.explanation?.data_quality_pct ?? "—"}%</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Historical effectiveness</p>
              <p className="font-medium">{recommendation.score?.explanation?.strategy_effectiveness_pct}%</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Evidence</p>
              <p className="font-medium capitalize">{recommendation.score?.explanation?.evidence_tier ?? "insufficient"}</p>
            </div>
          </div>

          {recommendation.alternatives?.length > 0 && (
            <div className="mt-4 border-t border-border pt-3">
              <p className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">Alternatives considered</p>
              <ul className="space-y-1.5 text-sm">
                {recommendation.alternatives.map((alt: any) => (
                  <li key={alt.action_type} className="flex items-center justify-between gap-2">
                    <span className="capitalize text-muted-foreground">{alt.action_type.replace(/_/g, " ")}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {typeof alt.effectiveness === "number" ? `${(alt.effectiveness * 100).toFixed(0)}% effectiveness` : "no evidence"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {/* Phase 7 §7: chronological decision timeline (evidence + decisions, no chain-of-thought). */}
      {timeline.length > 0 && (
        <Card density="editorial">
          <h2 className="mb-4 text-lg font-semibold text-foreground">Decision timeline</h2>
          <ol className="space-y-3">
            {timeline.map((e, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className={cn(
                  "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                  e.step === "rejected" || e.step === "failed" ? "bg-destructive" :
                  e.step === "learned" || e.step === "impact_measured" ? "bg-success" :
                  e.step === "approved" || e.step === "executed" ? "bg-secondary" : "bg-primary"
                )} />
                <div className="flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-foreground">{e.label}</span>
                    {e.at && <span className="text-xs text-muted-foreground">{new Date(e.at).toLocaleString()}</span>}
                  </div>
                  {e.rejection_reason && <p className="mt-0.5 text-xs text-muted-foreground">Reason: {e.rejection_reason}</p>}
                  {typeof e.actual_impact_sar === "number" && (
                    <p className="mt-0.5 text-xs text-success">Observed impact: SAR {money(e.actual_impact_sar)}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
