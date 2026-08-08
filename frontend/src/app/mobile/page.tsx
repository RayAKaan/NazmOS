"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  LayoutDashboard,
  Package,
  WalletCards,
  Repeat2,
  Sparkles,
  Download,
  CheckCircle2,
  XCircle,
  Bell,
} from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useAppStore } from "@/stores/appStore";
import { usePwaInstall } from "@/hooks/usePwaInstall";
import { cn } from "@/lib/utils";

interface FeedItem {
  id: string;
  action_type: string;
  title: string;
  summary: string;
  estimated_value_sar?: number;
  confidence: number;
  can_approve: boolean;
}

interface DashboardSummary {
  today: {
    sales: number;
    profit: number;
    transactions: number;
    avg_basket_size: number;
  };
  health_score: number;
}

function money(v: number | null | undefined) {
  return `﷼ ${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function MobilePage() {
  const { user, isAuthenticated, isLoading } = useAuth();
  const { businessId } = useAppStore();
  const { canInstall, isInstalled, promptInstall } = usePwaInstall();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!businessId) return;
    const load = async () => {
      try {
        const [sumRes, feedRes] = await Promise.all([
          api.get(`/dashboard/summary?business_id=${businessId}`),
          api.get(`/agent/feed?business_id=${businessId}&limit=10`),
        ]);
        setSummary(sumRes.data);
        setFeed(feedRes.data.items || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [businessId]);

  const approve = async (actionId: string) => {
    if (!businessId) return;
    try {
      await api.post(`/agent/actions/${actionId}/approve?business_id=${businessId}`);
      setNotice("Approved ✓");
      setFeed((prev) => prev.filter((i) => i.id !== actionId));
    } catch (err: any) {
      setNotice(err?.response?.data?.detail || "Could not approve");
    }
  };

  const reject = async (actionId: string) => {
    if (!businessId) return;
    try {
      await api.post(`/agent/actions/${actionId}/reject?business_id=${businessId}`);
      setNotice("Rejected ✗");
      setFeed((prev) => prev.filter((i) => i.id !== actionId));
    } catch (err: any) {
      setNotice(err?.response?.data?.detail || "Could not reject");
    }
  };

  if (isLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent-blue animate-pulse" />
          <p className="text-text-muted text-sm">Loading your briefing…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-6">
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold">NazmOS Mobile</h1>
          <p className="text-text-muted">Please log in to view your owner briefing.</p>
          <Link href="/login" className="inline-block rounded-xl bg-accent-blue px-6 py-3 text-white font-medium">
            Sign in
          </Link>
        </div>
      </div>
    );
  }

  const pending = feed.filter((i) => i.can_approve);
  const topAction = feed[0];

  return (
    <div className="min-h-screen bg-background pb-24 md:hidden">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-accent-blue flex items-center justify-center">
              <span className="text-white font-bold">ن</span>
            </div>
            <div>
              <p className="text-xs text-text-muted">NazmOS Mobile</p>
              <p className="text-sm font-semibold">Owner Briefing</p>
            </div>
          </div>
          {canInstall && (
            <button
              onClick={promptInstall}
              className="flex items-center gap-1 rounded-full bg-accent-blue/10 px-3 py-1.5 text-xs font-bold text-accent-blue"
            >
              <Download className="w-3.5 h-3.5" /> Install
            </button>
          )}
          {isInstalled && (
            <span className="text-xs text-text-muted">App installed</span>
          )}
        </div>
      </header>

      <main className="p-4 space-y-4">
        {notice && (
          <div className="rounded-xl border border-accent-blue/30 bg-accent-blue/10 px-4 py-2 text-sm text-accent-blue">
            {notice}
          </div>
        )}

        <section className="rounded-2xl border border-border bg-surface p-4">
          <p className="text-xs text-text-muted uppercase tracking-wider">Good {getGreeting()}</p>
          <h1 className="mt-1 text-xl font-bold">{user?.full_name?.split(" ")[0] || "Owner"}</h1>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Metric label="Today sales" value={money(summary?.today?.sales)} />
            <Metric label="Profit" value={money(summary?.today?.profit)} good />
            <Metric label="Transactions" value={String(summary?.today?.transactions || 0)} />
            <Metric label="Health" value={`${summary?.health_score ?? 0}/100`} />
          </div>
        </section>

        {topAction && (
          <section className="rounded-2xl border border-[#E0B34A]/30 bg-[#E0B34A]/10 p-4">
            <div className="flex items-center gap-2 text-[#E0B34A]">
              <Sparkles className="w-4 h-4" />
              <span className="text-xs font-bold uppercase tracking-wider">Top action</span>
            </div>
            <h2 className="mt-2 font-bold">{topAction.title}</h2>
            <p className="mt-1 text-sm text-text-secondary line-clamp-2">{topAction.summary}</p>
            <div className="mt-3 flex gap-2">
              {topAction.can_approve ? (
                <>
                  <button
                    onClick={() => approve(topAction.id)}
                    className="flex-1 rounded-xl bg-[#13A05A] py-2 text-sm font-bold text-black flex items-center justify-center gap-1"
                  >
                    <CheckCircle2 className="w-4 h-4" /> Approve
                  </button>
                  <button
                    onClick={() => reject(topAction.id)}
                    className="flex-1 rounded-xl border border-white/10 py-2 text-sm font-bold text-white/80 flex items-center justify-center gap-1"
                  >
                    <XCircle className="w-4 h-4" /> Reject
                  </button>
                </>
              ) : (
                <Link href="/feed" className="flex-1 rounded-xl bg-[#E0B34A] py-2 text-center text-sm font-bold text-black">
                  View in feed
                </Link>
              )}
            </div>
          </section>
        )}

        <section className="rounded-2xl border border-border bg-surface p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold flex items-center gap-2">
              <Bell className="w-4 h-4 text-accent-blue" /> Pending approvals
            </h2>
            <span className="text-xs text-text-muted">{pending.length}</span>
          </div>
          {pending.length === 0 && (
            <p className="text-sm text-text-muted">No pending approvals. Nazm is watching your store.</p>
          )}
          <div className="space-y-2">
            {pending.slice(0, 5).map((item) => (
              <div key={item.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-3">
                <p className="text-sm font-medium">{item.title}</p>
                <p className="text-xs text-text-muted line-clamp-1">{item.summary}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => approve(item.id)}
                    className="rounded-lg bg-[#13A05A] px-3 py-1 text-xs font-bold text-black"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => reject(item.id)}
                    className="rounded-lg border border-white/10 px-3 py-1 text-xs font-bold text-white/80"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        <nav className="grid grid-cols-4 gap-2">
          <MobileButton href="/dashboard" icon={LayoutDashboard} label="Home" />
          <MobileButton href="/money-audit" icon={WalletCards} label="Audit" />
          <MobileButton href="/inventory" icon={Package} label="Stock" />
          <MobileButton href="/recovery-match" icon={Repeat2} label="Match" />
        </nav>
      </main>
    </div>
  );
}

function Metric({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="rounded-xl bg-white/[0.03] p-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={cn("mt-1 text-lg font-bold", good && "text-accent-green")}>{value}</p>
    </div>
  );
}

function MobileButton({ href, icon: Icon, label }: { href: string; icon: React.ElementType; label: string }) {
  return (
    <Link
      href={href}
      className="flex flex-col items-center gap-1 rounded-xl border border-border bg-surface p-3 text-text-secondary"
    >
      <Icon className="w-5 h-5" />
      <span className="text-xs font-medium">{label}</span>
    </Link>
  );
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}
