"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  EyeOff,
  RefreshCw,
  ShieldAlert,
  Verified,
  Zap,
} from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { errorMessage, formatDate } from "@/lib/utils";
import RouteGuard from "@/components/RouteGuard";

interface CycleSummary {
  cycle_id: string;
  trigger: string;
  created_at: string;
  updated_at: string;
  completed: boolean;
  blocked: boolean;
  last_error_type: string;
  revalidation_blocked: boolean;
  lifecycle_status: string;
  flags: Record<string, boolean>;
  opportunity_type: string;
  impact_band: string | null;
  recommendation_status: string;
  execution: { executed: boolean; execution_failed: boolean; skipped: boolean };
  outcome: { verification_status: string; measured: boolean };
  learning_eligible: boolean;
  stage_index: number;
  stage_count: number;
}

interface SummaryResponse {
  configured: boolean;
  verified_rows: number;
  total_verified_impact_sar: number;
  learning_eligible_rows: number;
}

interface VerifiedRow {
  decision_key: string;
  actual_impact_sar: number | null;
  outcome_status?: string;
  verified?: boolean;
  recorded_at?: string;
}

interface PageResponse {
  items: CycleSummary[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

const BANDS: Record<string, string> = {
  under_250: "Under SAR 250",
  "250_999": "SAR 250 – 999",
  "1000_4999": "SAR 1k – 4.9k",
  "5000_plus": "SAR 5k+",
};

const LADDER_META: Record<string, { label: string; tone: string }> = {
  learning_eligible: { label: "Learning eligible", tone: "text-brand-green" },
  verified: { label: "Verified", tone: "text-brand-green" },
  measured: { label: "Measured", tone: "text-brand-amber" },
  executed: { label: "Executed", tone: "text-brand-amber" },
  blocked: { label: "Blocked", tone: "text-brand-red-light" },
  running: { label: "Running", tone: "text-brand-amber" },
  not_run: { label: "Not run", tone: "text-muted-foreground" },
};

function bandLabel(band: string | null) {
  return band ? BANDS[band] || band : "Not estimated";
}

function money(value: number | null | undefined) {
  return `SAR ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function LoopConsolePage() {
  const { businessId } = useAppStore();
  const [cycles, setCycles] = useState<CycleSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [verified, setVerified] = useState<VerifiedRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setError(null);
    try {
      const [pageRes, summaryRes, verifiedRes] = await Promise.all([
        api.get(`/loop-console/cycles?business_id=${businessId}&limit=100`),
        api.get(`/loop-console/summary?business_id=${businessId}`),
        api.get(`/loop-console/outcomes/verified?business_id=${businessId}`),
      ]);
      const page = pageRes.data as PageResponse;
      setCycles(page.items);
      setTotal(page.total);
      setSummary(summaryRes.data as SummaryResponse);
      setVerified((verifiedRes.data?.rows as VerifiedRow[]) || []);
    } catch (err: unknown) {
      setError(errorMessage(err, "Could not load the Loop Console."));
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    load();
  }, [load]);

  const verifiedRows = verified.filter((r) => r.verified);
  const learningRows = summary?.learning_eligible_rows ?? 0;
  const liveCount = cycles.filter((c) => c.lifecycle_status === "learning_eligible").length;
  const blockedCount = cycles.filter((c) => c.blocked).length;

  return (
    <RouteGuard>
      <div className="space-y-8">
        <section className="rounded-3xl border border-brand-cream/10 bg-brand-night p-6 text-brand-cream md:p-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">
                Business Loop Command Center
              </p>
              <h1 className="mt-3 font-serif text-4xl font-black tracking-[-0.04em] md:text-6xl">
                Watch the loop prove itself.
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-brand-cream/62">
                Read-only evidence from your own business loop: lifecycle ladder, execution
                receipts, verification, and outcome linkage. This console holds no authority —
                it never changes anything.
              </p>
            </div>
            <button
              onClick={load}
              className="inline-flex items-center gap-2 rounded-xl bg-brand-amber px-4 py-3 text-sm font-bold text-brand-night"
            >
              <RefreshCw className="h-4 w-4" /> Refresh
            </button>
          </div>
        </section>

        {loading ? (
          <div className="p-8 text-center text-muted-foreground">Loading loop console...</div>
        ) : error ? (
          <div className="rounded-3xl border border-brand-red/30 bg-brand-red/10 p-6 text-brand-cream">
            <h1 className="text-2xl font-bold">Loop Console unavailable</h1>
            <p className="mt-2 text-brand-cream/60">{error}</p>
          </div>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-4">
              <Kpi icon={Activity} label="Total cycles" value={String(total)} />
              <Kpi icon={CheckCircle2} label="Learning eligible" value={String(learningRows)} good={learningRows > 0} />
              <Kpi icon={Verified} label="Verified outcomes" value={String(verifiedRows.length)} good={verifiedRows.length > 0} />
              <Kpi
                icon={ShieldAlert}
                label="Blocked cycles"
                value={String(blockedCount)}
                danger={blockedCount > 0}
              />
            </section>

            <section>
              <Panel
                title="Cycle ladder"
                subtitle="Highest achieved lifecycle step per cycle, newest first (all of this is owner-gated read-only data)."
              >
                {cycles.length === 0 && <Empty text="No cycles have run yet. The loop will appear here the moment it runs." />}
                {cycles.map((cycle) => {
                  const meta = LADDER_META[cycle.lifecycle_status] || LADDER_META.not_run;
                  return (
                    <div key={cycle.cycle_id} className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-mono text-xs text-muted-foreground">{cycle.cycle_id}</p>
                            {cycle.revalidation_blocked && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-brand-red/10 px-2 py-0.5 text-xs font-bold text-brand-red-light">
                                <AlertTriangle className="h-3 w-3" /> Revalidation blocked
                              </span>
                            )}
                            {cycle.completed && (
                              <span className="rounded-full bg-brand-green/10 px-2 py-0.5 text-xs font-bold text-brand-green">
                                Completed
                              </span>
                            )}
                          </div>
                          <p className="mt-1 truncate font-bold text-brand-cream">
                            {cycle.opportunity_type || cycle.trigger || "Cycle"}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {formatDate(cycle.created_at)} · stage {cycle.stage_index + 1}/{cycle.stage_count} ·{" "}
                            {cycle.recommendation_status || "no recommendation"}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-wrap items-center gap-2">
                          <span className={meta.tone}>● {meta.label}</span>
                          <span className="rounded-full bg-brand-cream/10 px-3 py-1 text-xs font-bold text-brand-cream/60">
                            impact: {bandLabel(cycle.impact_band)}
                          </span>
                          {cycle.execution.executed && (
                            <span className="rounded-full bg-brand-amber/10 px-2 py-0.5 text-xs font-bold text-brand-amber">
                              executed
                            </span>
                          )}
                          {cycle.execution.skipped && (
                            <span className="rounded-full bg-brand-cream/10 px-2 py-0.5 text-xs font-bold text-muted-foreground">
                              skipped
                            </span>
                          )}
                          {cycle.execution.execution_failed && (
                            <span className="rounded-full bg-brand-red/10 px-2 py-0.5 text-xs font-bold text-brand-red-light">
                              execution failed
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </Panel>
            </section>

            <section className="grid gap-6 lg:grid-cols-2">
              <Panel
                title="Verified outcome linkage"
                subtitle="Rows your own cycle runs linked into the V1 OutcomeLedger (tenant-scoped; unrelated rows stay invisible)."
              >
                {!summary?.configured ? (
                  <div className="flex items-start gap-3 rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-4">
                    <EyeOff className="mt-0.5 h-5 w-5 text-muted-foreground" />
                    <div>
                      <p className="font-bold text-brand-cream">Ledger not configured</p>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        Verified capture is opt-in. When enabled, verified outcomes appear here — never a fabricated number.
                      </p>
                    </div>
                  </div>
                ) : verifiedRows.length === 0 ? (
                  <Empty text="No verified outcome rows linked to this business yet." />
                ) : (
                  <div className="space-y-3">
                    {verifiedRows.map((row) => (
                      <div key={row.decision_key} className="rounded-2xl border border-brand-green/15 bg-brand-green/[0.03] p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="font-mono text-xs text-muted-foreground">{row.decision_key}</p>
                            <p className="mt-1 text-xs text-brand-green/70">{row.outcome_status || "confirmed"}</p>
                          </div>
                          <p className="shrink-0 font-bold text-brand-green">
                            {row.actual_impact_sar != null ? money(row.actual_impact_sar) : "Not estimated"}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>

              <Panel
                title="Why this console stays read-only"
                subtitle="Observability is evidence; it is not authority."
              >
                <div className="space-y-3">
                  <Reason icon={CircleDot} title="Composes persisted state only">
                    Every number here is rebuilt from what the loop already wrote — the console never re-invents an
                    artifact and never calls the advisory/approval/execution surfaces to populate itself.
                  </Reason>
                  <Reason icon={Zap} title="DLP-clean by construction">
                    List views band impact instead of leaking exact SAR; SKUs and raw merchant payloads never leave the
                    evidence store.
                  </Reason>
                  <Reason icon={ShieldAlert} title="No authority, ever">
                    Anything this console shows you — an execution receipt, a verification, a learning-eligible badge — is
                    displayed exactly as the loop recorded it, with no button to change it.
                  </Reason>
                </div>
              </Panel>
            </section>
          </>
        )}
      </div>
    </RouteGuard>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  danger = false,
  good = false,
}: {
  icon: any;
  label: string;
  value: string;
  danger?: boolean;
  good?: boolean;
}) {
  const tone = danger ? "text-brand-red-light" : good ? "text-brand-green" : "text-brand-amber";
  return (
    <div className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.03] p-5">
      <Icon className={`h-5 w-5 ${tone}`} />
      <p className="mt-3 text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-black ${tone}`}>{value}</p>
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

function Reason({ icon: Icon, title, children }: { icon: any; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 rounded-2xl bg-brand-cream/[0.03] p-4 ring-1 ring-brand-cream/10">
      <Icon className="mt-0.5 h-5 w-5 text-brand-amber" />
      <div>
        <p className="font-bold text-brand-cream">{title}</p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-2xl border border-dashed border-brand-cream/10 p-6 text-center text-sm text-muted-foreground">{text}</div>;
}