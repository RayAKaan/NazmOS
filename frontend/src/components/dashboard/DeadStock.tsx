import { Trash2 } from "lucide-react";
import { Skeleton } from "@/components/ui/Skeleton";
import { DeadStockResponse } from "@/types/dashboard";
import { formatCurrency, cn } from "@/lib/utils";

interface DeadStockProps {
  data: DeadStockResponse | null;
  isLoading: boolean;
}

export function DeadStock({ data, isLoading }: DeadStockProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-28" />
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-12" />
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Trash2 className="w-5 h-5 text-text-muted" />
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider">
            Dead Stock
          </h3>
        </div>
        <div className="text-center py-8 text-text-muted">
          <p className="text-lg mb-2">🎉</p>
          <p>No dead stock found!</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Trash2 className="w-5 h-5 text-accent-red" />
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider">
          Dead Stock
        </h3>
      </div>
      <div className="space-y-2">
        {data.items.slice(0, 4).map((item) => (
          <div
            key={item.item_id}
            className="p-3 rounded-lg bg-accent-red/5 border border-accent-red/20"
          >
            <div className="flex items-start justify-between mb-1">
              <p className="font-medium text-sm">{item.name}</p>
              <span
                className={cn(
                  "text-xs px-2 py-0.5 rounded capitalize",
                  item.recommendation === "discount"
                    ? "bg-accent-yellow/10 text-accent-yellow"
                    : item.recommendation === "remove"
                    ? "bg-accent-red/10 text-accent-red"
                    : "bg-accent-purple/10 text-accent-purple"
                )}
              >
                {item.recommendation}
              </span>
            </div>
            <p className="text-xs text-text-muted">
              {item.days_since_last_sale || "∞"} days no sale •{" "}
              {formatCurrency(item.stock_value)} stuck
            </p>
          </div>
        ))}
      </div>
      {data.items.length > 0 && (
        <div className="mt-4 pt-3 border-t border-border">
          <p className="text-sm text-text-muted">
            Total stuck value:{" "}
            <span className="font-semibold text-accent-red">
              {formatCurrency(data.total_stuck_value)}
            </span>
          </p>
        </div>
      )}
    </div>
  );
}
