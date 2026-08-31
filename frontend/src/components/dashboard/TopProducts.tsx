import { Trophy } from "lucide-react";
import { Skeleton } from "@/components/ui/Skeleton";
import { TopProductsResponse } from "@/types/dashboard";
import { formatCurrency, cn } from "@/lib/utils";

interface TopProductsProps {
  data: TopProductsResponse | null;
  isLoading: boolean;
}

export function TopProducts({ data, isLoading }: TopProductsProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-28" />
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-12" />
        ))}
      </div>
    );
  }

  if (!data || data.products.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8">
        No sales data available
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Trophy className="w-5 h-5 text-warning" />
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Top Sellers
        </h3>
      </div>
      <div className="space-y-2">
        {data.products.slice(0, 5).map((product) => (
          <div
            key={product.item_id}
            className="flex items-center gap-3 p-3 rounded-lg bg-surface-hover/50 hover:bg-surface-hover transition-colors"
          >
            <div
              className={cn(
                "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold",
                product.rank === 1
                  ? "bg-warning/20 text-warning"
                  : product.rank === 2
                  ? "bg-muted/40 text-muted-foreground"
                  : product.rank === 3
                  ? "bg-warning/20 text-warning"
                  : "bg-surface text-muted-foreground"
              )}
            >
              {product.rank}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm truncate">{product.name}</p>
              <p className="text-xs text-muted-foreground">{product.category}</p>
            </div>
            <div className="text-right">
              <p className="font-semibold text-sm">
                {formatCurrency(product.total_revenue)}
              </p>
              <p className="text-xs text-muted-foreground">
                {product.total_qty.toFixed(0)} sold
              </p>
            </div>
            <div
              className={cn(
                "text-sm font-medium",
                product.trend === "up"
                  ? "text-success"
                  : product.trend === "down"
                  ? "text-destructive"
                  : "text-muted-foreground"
              )}
            >
              {product.trend === "up" ? "↑" : product.trend === "down" ? "↓" : "→"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
