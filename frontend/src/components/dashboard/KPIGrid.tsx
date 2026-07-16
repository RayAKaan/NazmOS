import { TrendingUp, TrendingDown, DollarSign, Activity } from "lucide-react";
import { KPICard } from "./KPICard";
import { Skeleton } from "@/components/ui/Skeleton";
import { DashboardSummary } from "@/types/dashboard";

interface KPIGridProps {
  summary: DashboardSummary | null;
  isLoading: boolean;
}

export function KPIGrid({ summary, isLoading }: KPIGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    );
  }

  if (!summary) return null;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <KPICard
        title="Today's Sales"
        value={summary.today.sales}
        change={summary.comparison.sales_change_percent}
        changeLabel="vs yesterday"
        accentColor="blue"
        icon={<TrendingUp className="w-5 h-5" />}
      />
      <KPICard
        title="This Month"
        value={summary.this_month.sales}
        prefix="﷼ "
        accentColor="green"
        icon={<DollarSign className="w-5 h-5" />}
      />
      <KPICard
        title="Profit"
        value={summary.this_month.profit}
        prefix="﷼ "
        change={summary.comparison.profit_change_percent}
        accentColor="yellow"
        icon={<TrendingDown className="w-5 h-5" />}
      />
      <KPICard
        title="Health Score"
        value={`${summary.health_score}/100`}
        accentColor={summary.health_score >= 70 ? "green" : summary.health_score >= 50 ? "yellow" : "purple"}
        icon={<Activity className="w-5 h-5" />}
      />
    </div>
  );
}
