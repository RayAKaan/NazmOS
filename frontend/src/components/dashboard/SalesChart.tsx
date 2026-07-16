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
      <div className="w-full h-[300px] flex items-center justify-center text-text-muted">
        No sales data available
      </div>
    );
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-surface border border-border rounded-lg p-3 shadow-lg">
          <p className="text-xs text-text-muted mb-2">{formatDate(label)}</p>
          <p className="text-sm font-medium text-accent-blue">
            Sales: {formatCurrency(payload[0].value)}
          </p>
          <p className="text-sm font-medium text-accent-green">
            Profit: {formatCurrency(payload[1]?.value || 0)}
          </p>
          <p className="text-xs text-text-secondary mt-1">
            {payload[2]?.value || 0} transactions
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider">
          Sales Trend
        </h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-accent-blue" />
            <span className="text-text-muted">Sales</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full bg-accent-green" />
            <span className="text-text-muted">Profit</span>
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
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorProfit" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
            <XAxis
              dataKey="date"
              stroke="#555570"
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
              stroke="#555570"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `SAR ${(value / 1000).toFixed(0)}K`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="sales"
              stroke="#3b82f6"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorSales)"
            />
            <Area
              type="monotone"
              dataKey="profit"
              stroke="#22c55e"
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
