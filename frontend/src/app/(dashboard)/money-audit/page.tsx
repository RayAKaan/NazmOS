"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clipboard,
  Download,
  FileSpreadsheet,
  MessageCircle,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  WalletCards,
  XCircle,
} from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { cn, errorMessage } from "@/lib/utils";
import { IntelligenceCard } from "@/components/intelligence/IntelligenceCard";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import { SeamBorder, type SeamState } from "@/components/ui/SeamBorder";
import { Sparkles } from "lucide-react";
import { MoneyRecoveryMap } from "@/components/money-audit/MoneyRecoveryMap";
import { TopDecisions } from "@/components/money-audit/TopDecisions";
import { DoNotDoThis } from "@/components/money-audit/DoNotDoThis";
import { TimeMachine } from "@/components/money-audit/TimeMachine";
import AIReasoningPanel from "@/components/money-audit/AIReasoningPanel";
import RecommendationInbox from "@/components/pilot/RecommendationInbox";
import BusinessConstraints from "@/components/pilot/BusinessConstraints";

interface AuditAction {
  id: string;
  action_type: string;
  priority: number;
  title: string;
  description?: string | null;
  expected_recovery_sar?: number | null;
  recoverable_value_low_sar?: number | null;
  recoverable_value_high_sar?: number | null;
  recovery_confidence?: string;
  financial_model?: Record<string, unknown>;
  quantity?: number | null;
  recommended_discount_pct?: number | null;
  status: "suggested" | "approved" | "rejected" | "completed" | string;
  item_name?: string | null;
}

interface MoneyAudit {
  id: string;
  status: string;
  period_start?: string | null;
  period_end?: string | null;
  money_at_risk_sar: number;
  inventory_value_sar: number;
  capital_at_risk_sar: number;
  revenue_at_risk_sar: number;
  gross_profit_at_risk_sar: number;
  recoverable_value_low_sar: number;
  recoverable_value_high_sar: number;
  expected_recovery_sar?: number | null;
  recovery_confidence: string;
  dead_stock_value_sar: number;
  stockout_risk_value_sar: number;
  margin_leakage_sar: number;
  overstock_value_sar: number;
  money_approved_sar: number;
  money_recovered_sar: number;
  confidence_score: number;
  data_quality_score: number;
  missing_data: { code: string; message: string }[];
  actions: AuditAction[];
  created_at?: string | null;
  intelligence_summary?: string | null;
  intelligence_actions?: { title: string; description?: string; expected_value_sar?: number; confidence?: number }[];
  intelligence_sources?: string[];
}

function money(value: number | null | undefined) {
  return `SAR ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function actionTone(type: string) {
  if (type === "reorder") return "text-brand-amber bg-brand-amber/10 border-brand-amber/25";
  if (type === "discount") return "text-brand-red-light bg-brand-red/10 border-brand-red/25";
  if (type === "margin_fix") return "text-brand-green bg-brand-green/10 border-brand-green/25";
  return "text-primary bg-primary/10 border-primary/20";
}

function statusTone(status: string) {
  if (status === "completed") return "text-brand-green bg-brand-green/10";
  if (status === "approved") return "text-brand-amber bg-brand-amber/10";
  if (status === "rejected") return "text-brand-cream/45 bg-brand-cream/10";
  return "text-primary bg-primary/10";
}

export default function MoneyAuditPage() {
  const { businessId } = useAppStore();
  const [audit, setAudit] = useState<MoneyAudit | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/money-audit/current?business_id=${businessId}&auto_generate=true`);
      setAudit(res.data);
    } catch (err: any) {
      setError(errorMessage(err, "Could not load Money Audit. Upload sales and inventory files first."));
      setAudit(null);
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    load();
  }, [load]);

  const regenerate = async () => {
    if (!businessId) return;
    setWorking(true);
    setNotice(null);
    try {
      const res = await api.post("/money-audit/generate", { business_id: businessId });
      setAudit(res.data);
      setNotice("New Money Audit generated from latest imported data.");
    } catch (err: any) {
      setNotice(err?.response?.data?.detail || "Could not generate audit yet.");
    } finally {
      setWorking(false);
    }
  };

  const updateAction = useCallback(async (actionId: string, status: "approve" | "reject" | "complete") => {
    if (!businessId) return;
    setWorking(true);
    setNotice(null);
    try {
      let body: any = { business_id: businessId, approval_channel: "dashboard" };
      if (status === "complete") {
        const value = window.prompt("Recovered/protected value in SAR:", "0");
        if (value === null) return;
        body.completed_value_sar = Number(value || 0);
        body.notes = "Completed from Money Audit dashboard";
      }
      const res = status === "approve"
        ? await api.post(`/money-audit/actions/${actionId}/approve`, body)
        : status === "reject"
          ? await api.post(`/money-audit/actions/${actionId}/reject`, body)
          : await api.post(`/money-audit/actions/${actionId}/complete`, body);
      setAudit(res.data);
      setNotice(status === "approve" ? "Action approved." : status === "reject" ? "Action rejected." : "Action marked completed.");
    } catch (err: any) {
      setNotice(err?.response?.data?.detail || "Could not update action.");
    } finally {
      setWorking(false);
    }
  }, [businessId]);

  const copyWhatsApp = async () => {
    if (!audit) return;
    setWorking(true);
    try {
      const res = await api.get(`/money-audit/${audit.id}/whatsapp-summary`, { responseType: "text" });
      await navigator.clipboard.writeText(res.data);
      setNotice("WhatsApp summary copied. Send it manually during pilot.");
    } catch {
      setNotice("Could not copy WhatsApp summary.");
    } finally {
      setWorking(false);
    }
  };

  const shareWhatsApp = async () => {
    if (!audit) return;
    setWorking(true);
    try {
      const res = await api.get(`/money-audit/${audit.id}/whatsapp-summary`, { responseType: "text" });
      const text = encodeURIComponent(res.data);
      window.open(`https://wa.me/?text=${text}`, "_blank", "noopener,noreferrer");
    } catch {
      setNotice("Could not open WhatsApp share.");
    } finally {
      setWorking(false);
    }
  };

  const openPrint = async () => {
    if (!audit) return;
    setWorking(true);
    try {
      const res = await api.get(`/money-audit/${audit.id}/print`, { responseType: "text" });
      const blob = new Blob([res.data], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setNotice("Could not open printable report.");
    } finally {
      setWorking(false);
    }
  };

  const suggested = useMemo(() => audit?.actions.filter((a) => a.status === "suggested") || [], [audit]);
  const approved = useMemo(() => audit?.actions.filter((a) => a.status === "approved") || [], [audit]);
  const completed = useMemo(() => audit?.actions.filter((a) => a.status === "completed") || [], [audit]);

  const auditId = audit?.id || null;

  const handleApprove = useCallback((actionId: string) => {
    updateAction(actionId, "approve");
  }, [updateAction]);

  const handleReject = useCallback((actionId: string) => {
    updateAction(actionId, "reject");
  }, [updateAction]);

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-14 w-14 animate-pulse rounded-2xl bg-brand-amber/20" />
          <p className="mt-4 text-text-muted">Generating Money Audit...</p>
        </div>
      </div>
    );
  }

  if (error && !audit) {
    return (
      <div className="space-y-6">
        <section className="rounded-3xl border border-brand-red/30 bg-brand-red/10 p-8 text-brand-cream">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-red-light">Money Audit unavailable</p>
          <h1 className="mt-3 text-3xl font-black">Upload sales and inventory files first.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-brand-cream/65">{error}</p>
          <a href="/upload" className="mt-6 inline-flex rounded-xl bg-brand-amber px-5 py-3 font-bold text-brand-night hover:bg-brand-gold">
            Upload files
          </a>
        </section>
      </div>
    );
  }

  if (!audit) return null;

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-3xl border border-brand-cream/10 bg-brand-night p-6 text-brand-cream shadow-2xl shadow-brand-night/20 md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">Free Money Audit</p>
            <h1 className="mt-4 max-w-4xl font-serif text-4xl font-black leading-tight tracking-[-0.04em] md:text-6xl">
              Here is the cash trapped inside your store.
            </h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-brand-cream/62">
              Generated from imported sales and inventory data. Founder-led pilots should review this before sending it to the merchant.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button disabled={working} onClick={regenerate} className="inline-flex items-center gap-2 rounded-xl border border-brand-cream/10 px-4 py-3 text-sm font-bold text-brand-cream/70 hover:bg-brand-cream/5">
              <RefreshCw className="h-4 w-4" /> Regenerate
            </button>
            <button disabled={working} onClick={copyWhatsApp} className="inline-flex items-center gap-2 rounded-xl border border-whatsapp/50 px-4 py-3 text-sm font-bold text-whatsapp hover:bg-whatsapp/10">
              <MessageCircle className="h-4 w-4" /> Copy WhatsApp
            </button>
            <button disabled={working} onClick={shareWhatsApp} className="inline-flex items-center gap-2 rounded-xl bg-whatsapp px-4 py-3 text-sm font-bold text-brand-night hover:bg-whatsapp-bright">
              <MessageCircle className="h-4 w-4" /> Share WhatsApp
            </button>
            <button disabled={working} onClick={openPrint} className="inline-flex items-center gap-2 rounded-xl bg-brand-amber px-4 py-3 text-sm font-bold text-brand-night hover:bg-brand-gold">
              <Download className="h-4 w-4" /> Printable report
            </button>
          </div>
        </div>
      </section>

      {notice && <div className="rounded-2xl border border-brand-amber/30 bg-brand-amber/10 p-4 text-sm text-brand-amber">{notice}</div>}

      <section className="grid gap-4 md:grid-cols-3">
        <Kpi icon={WalletCards} label="Capital at Risk" amount={audit.capital_at_risk_sar} tone="destructive" body="Inventory capital associated with a detected operational risk." />
        <Kpi icon={CheckCircle2} label="Potentially Recoverable" amount={audit.recoverable_value_high_sar} tone="warning" body={`Evidence-bounded range: ${money(audit.recoverable_value_low_sar)}–${money(audit.recoverable_value_high_sar)}. ${audit.recovery_confidence} confidence.`} />
        <Kpi icon={TrendingUp} label="Money Actually Recovered" amount={audit.money_recovered_sar} tone="success" body={`${completed.length} completed action(s). Only completed outcomes count as recovered.`} />
      </section>

      <section className="grid gap-4 md:grid-cols-5">
        <Mini label="Inventory value" value={money(audit.inventory_value_sar)} />
        <Mini label="Revenue at risk" value={money(audit.revenue_at_risk_sar)} />
        <Mini label="Gross profit at risk" value={money(audit.gross_profit_at_risk_sar)} />
        <Mini label="Recovery confidence" value={audit.recovery_confidence} />
        <Mini label="Data quality" value={`${Math.round(audit.data_quality_score || audit.confidence_score)}%`} />
      </section>

      {audit.intelligence_summary && (
        <IntelligenceCard
          title="AI-Powered Audit Summary"
          summary={audit.intelligence_summary}
          sources={audit.intelligence_sources || []}
          icon={<Sparkles className="w-5 h-5" />}
          variant="default"
        >
          {audit.intelligence_actions && audit.intelligence_actions.length > 0 && (
            <ul className="space-y-2">
              {audit.intelligence_actions.map((action, idx) => (
                <li key={idx} className="text-sm text-text-secondary">
                  <span className="text-text-primary font-medium">{action.title}</span>
                  {action.description && <> — {action.description}</>}
                  {typeof action.expected_value_sar === "number" && (
                    <span className="ml-2 text-status-success">
                      SAR {action.expected_value_sar.toLocaleString()}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </IntelligenceCard>
      )}

      {/* Money Recovery Map — "I FOUND WHERE YOUR MONEY IS TRAPPED" */}
      <MoneyRecoveryMap
        inventoryValue={audit.inventory_value_sar}
        deadStockValue={audit.dead_stock_value_sar}
        overstockValue={audit.overstock_value_sar}
        stockoutRiskValue={audit.stockout_risk_value_sar}
        marginLeakage={audit.margin_leakage_sar}
        capitalAtRisk={audit.capital_at_risk_sar}
        recoverableLow={audit.recoverable_value_low_sar}
        recoverableHigh={audit.recoverable_value_high_sar}
      />

      {/* Top 3 Decisions — "WHAT DESERVES YOUR ATTENTION" */}
      <TopDecisions
        decisions={audit.actions}
        onApprove={handleApprove}
        onReject={handleReject}
      />

      {/* One Thing I Would Not Do */}
      <DoNotDoThis decisions={audit.actions} />

      {/* What Happens If I Do Nothing? — Time Machine */}
      {auditId && businessId && (
        <TimeMachine auditId={auditId} businessId={businessId} />
      )}

      {/* Phase 5: controlled pilot workflow */}
      {businessId && <RecommendationInbox businessId={businessId} />}
      {businessId && <BusinessConstraints businessId={businessId} />}

      {/* V9: AI vs deterministic reasoning transparency */}
      {auditId && (
        <AIReasoningPanel auditId={auditId} />
      )}

      {audit.missing_data?.length > 0 && (
        <section className="rounded-3xl border border-brand-amber/25 bg-brand-amber/10 p-6">
          <div className="flex items-center gap-2 text-brand-amber">
            <AlertTriangle className="h-5 w-5" />
            <h2 className="text-xl font-bold">Data quality notes</h2>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {audit.missing_data.map((warning) => (
              <div key={warning.code} className="rounded-2xl bg-brand-night/20 p-4 text-sm leading-6 text-brand-cream/62">
                {warning.message}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-3xl border border-border bg-surface p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-bold">Recovery Actions</h2>
            <p className="mt-1 text-sm text-text-secondary">Approve, reject, or record a measured outcome. Only measured outcomes count as recovered.</p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full bg-brand-green/10 px-3 py-2 text-xs font-bold text-whatsapp-light">
            <ShieldCheck className="h-4 w-4" /> Owner stays in control
          </div>
        </div>

        <div className="mt-6 grid gap-4">
          {audit.actions.length === 0 && <EmptyActions />}
          {audit.actions.map((action) => (
            <ActionCard
              key={action.id}
              action={action}
              businessId={businessId}
              onApprove={() => updateAction(action.id, "approve")}
              onReject={() => updateAction(action.id, "reject")}
              onComplete={() => updateAction(action.id, "complete")}
              disabled={working}
            />
          ))}
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Workflow title="1. Founder review" body="Check top actions before sending report. Fix obvious bad mappings or missing cost data." icon={FileSpreadsheet} />
        <Workflow title="2. WhatsApp approval" body="Copy summary, send manually during pilot, log approvals in this page." icon={MessageCircle} />
        <Workflow title="3. Track recovery" body="Record measured outcome with recovered/protected value. This creates your case study proof." icon={TrendingDown} />
      </section>
    </div>
  );
}

function Kpi({ icon: Icon, label, amount, body, tone }: { icon: any; label: string; amount: number; body: string; tone: "destructive" | "warning" | "success" }) {
  const tones = {
    destructive: "text-brand-red-light",
    warning: "text-brand-amber",
    success: "text-brand-green",
  };
  return (
    <div className="rounded-3xl border border-brand-cream/10 bg-brand-night p-6 text-brand-cream">
      <Icon className={cn("h-6 w-6", tones[tone])} />
      <div className="mt-4">
        <FigureHeadline value={amount} currency="SAR" label={label} size="secondary" tone={tone} />
      </div>
      <p className="mt-3 text-sm leading-6 text-brand-cream/55">{body}</p>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-4">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-1 text-xl font-bold text-brand-cream">{value}</p>
    </div>
  );
}

function ActionCard({ action, businessId, onApprove, onReject, onComplete, disabled }: { action: AuditAction; businessId: string | null; onApprove: () => void; onReject: () => void; onComplete: () => void; disabled: boolean }) {
  const [scenarios, setScenarios] = useState<any[] | null>(null);
  const [simulating, setSimulating] = useState(false);
  const simulate = async () => {
    if (!businessId) return;
    setSimulating(true);
    try {
      const response = await api.post(`/api/v1/money-audit/actions/${action.id}/simulate`, { business_id: businessId });
      setScenarios(response.data?.options || []);
    } finally {
      setSimulating(false);
    }
  };
  const canApprove = action.status === "suggested";
  const canComplete = action.status === "approved";
  const canReject = action.status !== "rejected" && action.status !== "completed";
  // §1 kintsugi: only Money Audit / Recovery Match render SeamBorder. A card moving
  // suggested → approved → completed draws the gold seam once on the recovered state.
  const seamState: SeamState =
    action.status === "completed" ? "recovered" : action.status === "approved" ? "resolving" : "idle";
  return (
    <SeamBorder state={seamState} className="p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn("rounded-full border px-3 py-1 text-xs font-bold", actionTone(action.action_type))}>{action.action_type.replaceAll("_", " ")}</span>
            <span className={cn("rounded-full px-3 py-1 text-xs font-bold", statusTone(action.status))}>{action.status.replaceAll("_", " ")}</span>
            <span className="rounded-full bg-brand-cream/10 px-3 py-1 text-xs font-bold text-brand-cream/50">Priority {action.priority}</span>
          </div>
          <h3 className="mt-3 text-lg font-bold text-brand-cream">{action.title}</h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">{action.description}</p>
        </div>
        <div className="shrink-0 rounded-2xl bg-brand-night/20 p-4 text-right">
          <p className="text-xs text-text-muted">Expected recovery</p>
          <p className="mt-1 text-2xl font-black text-brand-green">{action.expected_recovery_sar != null ? money(action.expected_recovery_sar) : "Not estimated"}</p>
          <p className="mt-1 text-xs text-text-muted">{action.recoverable_value_low_sar != null || action.recoverable_value_high_sar != null ? `Range ${money(action.recoverable_value_low_sar)}–${money(action.recoverable_value_high_sar)}` : "Insufficient evidence for a recovery estimate"}</p>
          <p className="mt-1 text-xs font-bold text-text-muted">{action.recovery_confidence || "INSUFFICIENT DATA"}</p>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {canApprove && <button disabled={disabled} onClick={onApprove} className="rounded-xl bg-whatsapp px-4 py-2 text-sm font-bold text-brand-night">Approve</button>}
        {canComplete && <button disabled={disabled} onClick={onComplete} className="rounded-xl bg-brand-green px-4 py-2 text-sm font-bold text-brand-night">Record measured outcome</button>}
        {canReject && <button disabled={disabled} onClick={onReject} className="inline-flex items-center gap-2 rounded-xl border border-brand-cream/10 px-4 py-2 text-sm font-bold text-brand-cream/70 hover:bg-brand-cream/5"><XCircle className="h-4 w-4" /> Reject</button>}
        <button disabled={disabled} onClick={() => navigator.clipboard.writeText(`${action.title}\n${action.description || ""}\nExpected: ${action.expected_recovery_sar != null ? money(action.expected_recovery_sar) : "not estimated"}`)} className="inline-flex items-center gap-2 rounded-xl border border-brand-cream/10 px-4 py-2 text-sm font-bold text-brand-cream/70 hover:bg-brand-cream/5">
          <Clipboard className="h-4 w-4" /> Copy action
        </button>
        <button disabled={disabled || simulating || !businessId} onClick={simulate} className="inline-flex items-center gap-2 rounded-xl border border-brand-cream/10 px-4 py-2 text-sm font-bold text-brand-cream/70 hover:bg-brand-cream/5">
          {simulating ? "Simulating…" : "Compare scenarios"}
        </button>
      </div>
      {scenarios && scenarios.length > 0 && (
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          {scenarios.map((scenario: any) => (
            <div key={scenario.name} className="rounded-xl border border-brand-cream/10 bg-brand-cream/[0.03] p-3">
              <p className="text-xs font-bold text-brand-cream">{scenario.name}</p>
              <p className="mt-1 text-sm text-brand-green">{scenario.expected_recovery_sar != null ? money(scenario.expected_recovery_sar) : `${money(scenario.low_sar)}–${money(scenario.high_sar)}`}</p>
              <p className="mt-1 text-[11px] text-text-muted">Estimate only · {scenario.confidence}</p>
            </div>
          ))}
        </div>
      )}
    </SeamBorder>
  );
}

function Workflow({ title, body, icon: Icon }: { title: string; body: string; icon: any }) {
  return (
    <div className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-5">
      <Icon className="h-5 w-5 text-brand-amber" />
      <h3 className="mt-3 font-bold text-brand-cream">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-text-secondary">{body}</p>
    </div>
  );
}

function EmptyActions() {
  return (
    <div className="rounded-2xl border border-dashed border-brand-cream/10 p-8 text-center">
      <p className="font-bold text-brand-cream">No actions generated yet.</p>
      <p className="mt-1 text-sm text-text-muted">Upload sales and inventory data with cost/current stock for a useful audit.</p>
    </div>
  );
}
