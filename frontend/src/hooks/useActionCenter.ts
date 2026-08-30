"use client";

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";

interface ActionReport {
  overall_health: number;
  critical: number;
  important: number;
  watch: number;
  capital_at_risk_sar: number;
  impact?: { total_sar: number; observed_sar: number; estimated_sar: number };
}

interface Finding {
  id: string;
  title: string;
  domain: string;
  category: string;
  severity: string;
  status: string;
  estimated_financial_impact_sar: number | null;
}

interface Approval {
  id: string;
  title: string;
  summary: string;
  can_approve: boolean;
  estimated_value_sar: number | null;
}

interface Goal {
  id: string;
  title: string;
  trajectory: string | null;
  progress_pct: number | null;
}

interface HealthTrend {
  current_health: number;
  previous_health: number;
  trend: "up" | "down" | "flat";
  delta: number;
  note: string;
}

interface Comparison {
  counts: {
    new: number;
    improving: number;
    worsening: number;
    resolved: number;
    recurring: number;
    persistent: number;
  };
  findings: { id: string; title: string; status: string }[];
}

interface Learning {
  attempts: number;
  succeeded: number;
  rejected: number;
  success_rate: number | null;
  effectiveness: number | null;
  total_actual_impact_sar: number;
}

interface Strategy {
  action_type: string;
  success_rate: number | null;
  effectiveness: number | null;
  evidence_tier: string;
}

interface Ops {
  status: string;
  merchant_summary: string;
}

interface ActionCenterState {
  report: ActionReport | null;
  impact: { total_sar: number; observed_sar: number; estimated_sar: number } | null;
  findings: Finding[];
  approvals: Approval[];
  goals: Goal[];
  healthTrend: HealthTrend | null;
  comparison: Comparison | null;
  learning: Learning;
  strategies: Strategy[];
  ops: Ops | null;
  isLoading: boolean;
  refresh: () => Promise<void>;
}

const emptyLearning: Learning = {
  attempts: 0,
  succeeded: 0,
  rejected: 0,
  success_rate: null,
  effectiveness: null,
  total_actual_impact_sar: 0,
};

export function useActionCenter(): ActionCenterState {
  const { businessId } = useAppStore();
  const [state, setState] = useState<ActionCenterState>({
    report: null,
    impact: null,
    findings: [],
    approvals: [],
    goals: [],
    healthTrend: null,
    comparison: null,
    learning: emptyLearning,
    strategies: [],
    ops: null,
    isLoading: true,
    refresh: async () => {},
  });

  const fetchData = useCallback(async () => {
    if (!businessId) {
      setState((s) => ({ ...s, isLoading: false }));
      return;
    }

    setState((s) => ({ ...s, isLoading: true }));

    const [summaryRes, feedRes, findingsRes] = await Promise.allSettled([
      api.get("/dashboard/summary", { params: { business_id: businessId } }),
      api.get("/agent/feed", { params: { business_id: businessId, limit: 20 } }),
      api.get("/audits/runs", { params: { business_id: businessId, limit: 1 } }),
    ]);

    const summary =
      summaryRes.status === "fulfilled" ? summaryRes.value.data : null;
    const feed =
      feedRes.status === "fulfilled" ? feedRes.value.data : null;
    const audits =
      findingsRes.status === "fulfilled" ? findingsRes.value.data?.runs ?? null : null;

    const report: ActionReport | null = summary
      ? {
          overall_health: summary.health_score ?? 0,
          critical: summary.critical_alerts ?? 0,
          important: summary.important_alerts ?? 0,
          watch: summary.watch_items ?? 0,
          capital_at_risk_sar: summary.capital_at_risk_sar ?? 0,
          impact: summary.impact,
        }
      : null;

    const findings: Finding[] = feed?.findings ?? [];
    const approvals: Approval[] = (feed?.actions ?? []).map(
      (a: Record<string, unknown>) => ({
        id: a.id as string,
        title: a.title as string,
        summary: (a.summary as string) ?? "",
        can_approve:
          (a.status as string) === "pending_approval" ||
          (a.status as string) === "suggested",
        estimated_value_sar: (a.estimated_value_sar as number) ?? null,
      })
    );

    const impact = report?.impact ?? null;

    setState({
      report,
      impact,
      findings,
      approvals,
      goals: [],
      healthTrend: null,
      comparison: null,
      learning: emptyLearning,
      strategies: [],
      ops: null,
      isLoading: false,
      refresh: fetchData,
    });
  }, [businessId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { ...state, refresh: fetchData };
}
