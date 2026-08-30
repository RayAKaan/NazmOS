import { Skeleton } from "@/components/ui/Skeleton";
import { BentoGrid } from "@/components/ui/BentoGrid";
import { Card } from "@/components/ui/Card";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import { DashboardSummary } from "@/types/dashboard";

interface KPIGridProps {
  summary: DashboardSummary | null;
  isLoading: boolean;
}

/**
 * KPI section on the shared BentoGrid + FigureHeadline primitives (v2 §5 + v3 §A/B).
 * Each KPI card is level-2 elevation (Card trim="weave") with a count-up headline.
 */
export function KPIGrid({ summary, isLoading }: KPIGridProps) {
  if (isLoading) {
    return (
      <BentoGrid cols={{ base: 1, md: 2, lg: 4 }} gap={6}>
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-36" />
        ))}
      </BentoGrid>
    );
  }

  if (!summary) return null;

  const salesChange = summary.comparison.sales_change_percent;
  const profitChange = summary.comparison.profit_change_percent;

  return (
    <BentoGrid cols={{ base: 1, md: 2, lg: 4 }} gap={6}>
      <Card density="editorial" trim="weave">
        <FigureHeadline
          value={summary.today.sales}
          currency="SAR"
          label="Today's Sales"
          trend={{
            direction: salesChange >= 0 ? "up" : "down",
            percent: Math.abs(salesChange),
          }}
        />
      </Card>

      <Card density="editorial" trim="weave">
        <FigureHeadline value={summary.this_month.sales} currency="SAR" label="This Month" />
      </Card>

      <Card density="editorial" trim="weave">
        <FigureHeadline
          value={summary.this_month.profit}
          currency="SAR"
          label="Profit"
          trend={{
            direction: profitChange >= 0 ? "up" : "down",
            percent: Math.abs(profitChange),
          }}
        />
      </Card>

      <Card density="editorial" trim="weave">
        <FigureHeadline value={summary.health_score} currency="/100" label="Health Score" />
      </Card>
    </BentoGrid>
  );
}
