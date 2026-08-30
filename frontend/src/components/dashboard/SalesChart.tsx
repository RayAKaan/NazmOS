"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Skeleton } from "@/components/ui/Skeleton";
import { Card } from "@/components/ui/Card";
import { SalesTrend } from "@/types/dashboard";
import { formatCurrency, formatDate } from "@/lib/utils";

interface SalesChartProps {
  data: SalesTrend | null;
  isLoading: boolean;
}

export function SalesChart({ data, isLoading }: SalesChartProps) {
  if (isLoading) {
    return <Skeleton className="w-full h-[300px]" />;
  }

  if (!data || data.data.length === 0) {
    return (
      <div className="w-full h-[300px] flex items-center justify-center text-muted-foreground">
        No sales data available
      </div>
    );
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <Card density="data" className="shadow-elevation-2">
          <p className="text-xs text-muted-foreground mb-2">{formatDate(label)}</p>
          <p className="text-sm font-medium text-chart-3">
            Sales: {formatCurrency(payload[0].value)}
          </p>
          <p className="text-sm font-medium text-chart-1">
            Profit: {formatCurrency(payload[1]?.value || 0)}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {payload[2]?.value || 0} transactions
          </p>
        </Card>
      );
    }
    return null;
  };

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Sales Trend
        </h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-chart-3" />
            <span className="text-muted-foreground">Sales</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-chart-1" />
            <span className="text-muted-foreground">Profit</span>
          </div>
        </div>
      </div>
      <div className="h-[250px] md:h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data.data}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="colorSales" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--chart-3)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--chart-3)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorProfit" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
            <XAxis
              dataKey="date"
              stroke="var(--muted-foreground)"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => {
                const date = new Date(value);
                return `${date.getDate()}/${date.getMonth() + 1}`;
              }}
              interval="preserveStartEnd"
            />
            <YAxis
              stroke="var(--muted-foreground)"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `SAR ${(value / 1000).toFixed(0)}K`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="sales"
              stroke="var(--chart-3)"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorSales)"
            />
            <Area
              type="monotone"
              dataKey="profit"
              stroke="var(--chart-1)"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorProfit)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
