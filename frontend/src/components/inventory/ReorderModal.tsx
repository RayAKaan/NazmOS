"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { StockStatusBadge } from "./StockStatusBadge";
import { ItemDetail } from "@/types/inventory";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface ReorderModalProps {
  item: ItemDetail | null;
  isOpen: boolean;
  onClose: () => void;
}

export function ReorderModal({ item, isOpen, onClose }: ReorderModalProps) {
  if (!isOpen || !item) return null;

  const { item: itemData, sales_history_30d, forecast_7d, reorder_recommendation } = item;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-overlay backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-surface border border-border rounded-2xl shadow-xl">
        <div className="sticky top-0 bg-surface border-b border-border p-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold">{itemData.name}</h2>
            <p className="text-sm text-text-muted">{itemData.category}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-surface-hover transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-6">
          <div className="flex items-center gap-4">
            <StockStatusBadge status={itemData.status} />
            <span className="text-sm text-text-muted">
              SKU: {itemData.sku || "N/A"}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-lg bg-background">
              <p className="text-xs text-text-muted mb-1">Current Stock</p>
              <p className="text-lg font-bold">
                {itemData.current_stock.toFixed(0)} {itemData.unit}
              </p>
            </div>
            <div className="p-4 rounded-lg bg-background">
              <p className="text-xs text-text-muted mb-1">Daily Average</p>
              <p className="text-lg font-bold">{itemData.daily_avg_sale} {itemData.unit}</p>
            </div>
            <div className="p-4 rounded-lg bg-background">
              <p className="text-xs text-text-muted mb-1">Days Left</p>
              <p className="text-lg font-bold">
                {itemData.days_until_stockout?.toFixed(1) || "∞"}
              </p>
            </div>
            <div className="p-4 rounded-lg bg-background">
              <p className="text-xs text-text-muted mb-1">Stock Value</p>
              <p className="text-lg font-bold">{formatCurrency(itemData.stock_value)}</p>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3">
              Sales History (30 Days)
            </h3>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sales_history_30d}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis
                    dataKey="date"
                    stroke="var(--muted-foreground)"
                    fontSize={10}
                    tickLine={false}
                    tickFormatter={(value) => {
                      const date = new Date(value);
                      return `${date.getDate()}/${date.getMonth() + 1}`;
                    }}
                  />
                  <YAxis stroke="var(--muted-foreground)" fontSize={10} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--background)",
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="quantity"
                    stroke="var(--chart-3)"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {reorder_recommendation.should_reorder && (
            <div className="p-4 rounded-xl bg-accent-yellow/10 border border-accent-yellow/30">
              <h4 className="font-semibold text-accent-yellow mb-2">Reorder Recommendation</h4>
              <p className="text-sm text-text-secondary mb-2">
                {reorder_recommendation.reason}
              </p>
              <p className="text-sm">
                <span className="text-text-muted">Recommended Quantity:</span>{" "}
                <span className="font-semibold">{reorder_recommendation.recommended_qty} {itemData.unit}</span>
              </p>
              {reorder_recommendation.recommended_by_date && (
                <p className="text-sm">
                  <span className="text-text-muted">Order By:</span>{" "}
                  <span className="font-semibold">{formatDate(reorder_recommendation.recommended_by_date)}</span>
                </p>
              )}
              <Button className="mt-3" size="sm">
                Create Reorder
              </Button>
            </div>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-border">
            <div className="text-sm text-text-muted">
              <p>Last Restocked: {itemData.last_restocked ? formatDate(itemData.last_restocked) : "N/A"}</p>
              <p>Trend: {itemData.trend_7d === "up" ? "📈 Trending Up" : itemData.trend_7d === "down" ? "📉 Trending Down" : "➡️ Stable"}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
