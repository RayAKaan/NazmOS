"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ClipboardList, FileSpreadsheet, RefreshCw, ShieldAlert, WalletCards } from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { errorMessage } from "@/lib/utils";
import RouteGuard from "@/components/RouteGuard";

interface OpsData {
  upload_counts: Record<string, number>;
  recent_uploads: any[];
  latest_audit: any | null;
  action_queue: any[];
  recovery_issues: any[];
  operator_next_steps: string[];
}

function money(value: number | null | undefined) {
  return `SAR ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function OpsPage() {
  const { businessId } = useAppStore();
  const [data, setData] = useState<OpsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/ops/pilot-console?business_id=${businessId}`);
      setData(res.data);
    } catch (err: any) {
      setError(errorMessage(err, "Could not load pilot console."));
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground">Loading pilot console...</div>;
  }

  if (error || !data) {
    return (
      <div className="rounded-3xl border border-brand-red/30 bg-brand-red/10 p-6 text-brand-cream">
        <h1 className="text-2xl font-bold">Pilot console unavailable</h1>
        <p className="mt-2 text-brand-cream/60">{error}</p>
      </div>
    );
  }

  const failedUploads = data.upload_counts.failed || 0;
  const completedUploads = data.upload_counts.completed || 0;
  const pendingActions = data.action_queue.filter((a) => a.status === "suggested").length;

  return (
    <RouteGuard require="can_view_ops_console">
      <div className="space-y-8">
      <section className="rounded-3xl border border-brand-cream/10 bg-brand-night p-6 text-brand-cream md:p-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">Founder pilot console</p>
            <h1 className="mt-3 font-serif text-4xl font-black tracking-[-0.04em] md:text-6xl">Operate the pilot safely.</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-brand-cream/62">
              Failed uploads, audit queue, pending recovery actions, and Recovery Match issues in one place.
            </p>
          </div>
          <button onClick={load} className="inline-flex items-center gap-2 rounded-xl bg-brand-amber px-4 py-3 text-sm font-bold text-brand-night">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <Kpi icon={FileSpreadsheet} label="Completed uploads" value={String(completedUploads)} />
        <Kpi icon={AlertTriangle} label="Failed uploads" value={String(failedUploads)} danger={failedUploads > 0} />
        <Kpi icon={WalletCards} label="Capital at Risk" value={money(data.latest_audit?.capital_at_risk_sar ?? data.latest_audit?.money_at_risk_sar)} />
        <Kpi icon={ClipboardList} label="Pending actions" value={String(pendingActions)} />
      </section>

      <section className="grid gap-6 lg:grid-cols-[1fr_.9fr]">
        <Panel title="Recent uploads" subtitle="Fix bad imports before the merchant call.">
          <div className="space-y-3">
            {data.recent_uploads.length === 0 && <Empty text="No uploads yet." />}
            {data.recent_uploads.map((upload) => (
              <div key={upload.upload_id} className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-4">
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="font-bold text-brand-cream">{upload.filename}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{upload.row_count_imported || 0} imported · {upload.row_count_failed || 0} failed</p>
                  </div>
                  <span className="rounded-full bg-brand-cream/10 px-3 py-1 text-xs font-bold text-brand-cream/60">{upload.status}</span>
                </div>
                {upload.error_summary && <p className="mt-3 text-sm text-brand-red-light">{upload.error_summary}</p>}
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Operator next steps" subtitle="This keeps pilots founder-controlled.">
          <div className="space-y-3">
            {data.operator_next_steps.map((step, index) => (
              <div key={step} className="flex gap-3 rounded-2xl bg-brand-cream/[0.03] p-4 ring-1 ring-brand-cream/10">
                <CheckCircle2 className="mt-0.5 h-5 w-5 text-brand-green" />
                <div>
                  <p className="font-bold text-brand-cream">Step {index + 1}</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">{step}</p>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <Panel title="Money Audit action queue" subtitle="Suggested and approved actions waiting for owner/founder follow-up.">
          <div className="space-y-3">
            {data.action_queue.length === 0 && <Empty text="No pending actions. Generate a Money Audit first." />}
            {data.action_queue.map((action) => (
              <div key={action.id} className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-bold text-brand-cream">{action.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{action.action_type} · priority {action.priority}</p>
                  </div>
                  <p className="shrink-0 font-bold text-brand-green">{action.expected_recovery_sar != null ? money(action.expected_recovery_sar) : "Not estimated"}</p>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Recovery Match issues" subtitle="Do not scale R2R until issue handling is clean.">
          <div className="space-y-3">
            {data.recovery_issues.length === 0 && <Empty text="No reported Recovery Match issues." />}
            {data.recovery_issues.map((issue) => (
              <div key={issue.id} className="rounded-2xl border border-brand-red/25 bg-brand-red/10 p-4">
                <div className="flex gap-3">
                  <ShieldAlert className="mt-0.5 h-5 w-5 text-brand-red-light" />
                  <div>
                    <p className="font-bold text-brand-cream">{issue.payload?.issue_type || "Issue reported"}</p>
                    <p className="mt-1 text-sm leading-6 text-brand-cream/60">{issue.notes || "Founder review required."}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </section>
      </div>
    </RouteGuard>
  );
}

function Kpi({ icon: Icon, label, value, danger = false }: { icon: any; label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-5">
      <Icon className={danger ? "h-5 w-5 text-brand-red-light" : "h-5 w-5 text-brand-amber"} />
      <p className="mt-3 text-xs text-muted-foreground">{label}</p>
      <p className={danger ? "mt-1 text-2xl font-black text-brand-red-light" : "mt-1 text-2xl font-black text-brand-cream"}>{value}</p>
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="text-2xl font-bold text-brand-cream">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-2xl border border-dashed border-brand-cream/10 p-6 text-center text-sm text-muted-foreground">{text}</div>;
}
