"use client";

import { KPIGrid } from "@/components/dashboard/KPIGrid";
import { AlertSection } from "@/components/dashboard/AlertSection";
import { SalesChart } from "@/components/dashboard/SalesChart";
import { TopProducts } from "@/components/dashboard/TopProducts";
import { DeadStock } from "@/components/dashboard/DeadStock";
import { QuickActions } from "@/components/dashboard/QuickActions";
import { HealthScore } from "@/components/dashboard/HealthScore";
import { useDashboard } from "@/hooks/useDashboard";
import { useAuth } from "@/hooks/useAuth";
import { getGreeting } from "@/lib/utils";
import { FreeAuditChecklist } from "@/components/free/FreeAuditChecklist";
import { MoneyAuditEmptyState } from "@/components/free/MoneyAuditEmptyState";

export default function DashboardPage() {
  const { user } = useAuth();
  const {
    summary,
    alerts,
    salesTrend,
    topProducts,
    deadStock,
    hourlyPattern,
    categoryBreakdown,
    isLoading,
    error,
  } = useDashboard();

  const hasUsableData = Boolean(
    summary && (summary.today.transactions > 0 || summary.this_month.transactions > 0)
  );

  if (error) {
    return (
      <div className="space-y-6 animate-in">
        <div className="rounded-3xl border border-[#C8412A]/30 bg-[#C8412A]/10 p-6 text-white">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-[#ff8a73]">Dashboard data not loaded</p>
          <h1 className="mt-3 text-2xl font-black">NazmOS could not load this store overview.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/60">
            {error}. If this is a new merchant account, start with the Free Money Audit upload.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <button onClick={() => window.location.reload()} className="rounded-xl bg-[#E0B34A] px-4 py-2 font-bold text-black">
              Retry
            </button>
            <a href="/upload" className="rounded-xl border border-white/10 px-4 py-2 font-bold text-white/75 hover:bg-white/5">
              Upload files
            </a>
          </div>
        </div>
        <FreeAuditChecklist />
      </div>
    );
  }

  if (!isLoading && !hasUsableData) {
    return (
      <div className="space-y-6 animate-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">
              {getGreeting()}, {user?.full_name?.split(" ")[0] || "User"}
            </h1>
            <p className="text-text-muted">Let&apos;s create your first Money Audit.</p>
          </div>
        </div>
        <MoneyAuditEmptyState />
        <FreeAuditChecklist />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">
            {getGreeting()}, {user?.full_name?.split(" ")[0] || "User"}
          </h1>
          <p className="text-text-muted">Here&apos;s your store overview</p>
        </div>
      </div>

      <FreeAuditChecklist />

      <KPIGrid summary={summary} isLoading={isLoading} />

      <AlertSection alerts={alerts} isLoading={isLoading} />

      <div className="p-5 rounded-xl bg-surface border border-border">
        <SalesChart data={salesTrend} isLoading={isLoading} />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="p-5 rounded-xl bg-surface border border-border">
          <TopProducts data={topProducts} isLoading={isLoading} />
        </div>
        <div className="p-5 rounded-xl bg-surface border border-border">
          <DeadStock data={deadStock} isLoading={isLoading} />
        </div>
      </div>

      <div className="p-5 rounded-xl bg-surface border border-border">
        <QuickActions />
      </div>

      {summary && (
        <div className="grid md:grid-cols-2 gap-6">
          <HealthScore score={summary.health_score} isLoading={isLoading} />
          <div className="p-5 rounded-xl bg-surface border border-border">
            <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">
              Today&apos;s Stats
            </h3>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-text-secondary">Transactions</span>
                <span className="font-semibold">{summary.today.transactions}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-text-secondary">Avg Basket Size</span>
                <span className="font-semibold">﷼ {summary.today.avg_basket_size.toFixed(0)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-text-secondary">Today&apos;s Profit</span>
                <span className="font-semibold text-accent-green">﷼ {summary.today.profit.toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
