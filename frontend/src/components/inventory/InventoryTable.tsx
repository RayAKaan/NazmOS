import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Package } from "lucide-react";
import { InventoryResponse } from "@/types/inventory";
import { formatCurrency, cn } from "@/lib/utils";

interface InventoryTableProps {
  data: InventoryResponse | null;
  isLoading: boolean;
  onItemClick?: (itemId: string) => void;
}

export function InventoryTable({ data, isLoading, onItemClick }: InventoryTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        icon={Package}
        title="No inventory items found"
        description="Upload your inventory snapshot to start tracking stock levels, critical counts, and recovery opportunities."
        actions={[{ label: "Upload files", href: "/upload", primary: true }]}
        className="border-0 bg-transparent"
      />
    );
  }

  const statusBadge = (status: string) => {
    const variants: Record<string, "danger" | "warning" | "success" | "purple" | "default"> = {
      critical: "danger",
      low: "warning",
      healthy: "success",
      overstock: "purple",
      dead: "default",
    };
    const labels: Record<string, string> = {
      critical: "Critical",
      low: "Low",
      healthy: "OK",
      overstock: "Over",
      dead: "Dead",
    };
    return <Badge variant={variants[status]}>{labels[status]}</Badge>;
  };

  return (
    <div className="overflow-x-auto -mx-4 md:mx-0">
      <table className="w-full min-w-[600px] md:min-w-0">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left p-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Item
            </th>
            <th className="text-right p-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Stock
            </th>
            <th className="text-right p-3 text-xs font-medium text-muted-foreground uppercase tracking-wider hidden sm:table-cell">
              Daily Avg
            </th>
            <th className="text-right p-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Days Left
            </th>
            <th className="text-center p-3 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Status
            </th>
            <th className="text-right p-3 text-xs font-medium text-muted-foreground uppercase tracking-wider hidden md:table-cell">
              Value
            </th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item) => (
            <tr
              key={item.item_id}
              onClick={() => onItemClick?.(item.item_id)}
              className="border-b border-border/50 hover:bg-surface-hover cursor-pointer transition-colors"
            >
              <td className="p-3">
                <div>
                  <p className="font-medium text-sm">{item.name}</p>
                  <p className="text-xs text-muted-foreground">{item.category}</p>
                </div>
              </td>
              <td className="p-3 text-right">
                <span className="font-medium">
                  {item.current_stock.toFixed(0)}
                </span>
                <span className="text-muted-foreground text-xs ml-1">{item.unit}</span>
              </td>
              <td className="p-3 text-right hidden sm:table-cell">
                {item.daily_avg_sale.toFixed(1)}/day
              </td>
              <td className="p-3 text-right">
                <span
                  className={cn(
                    "font-medium",
                    item.days_until_stockout !== null &&
                      item.days_until_stockout < 3 &&
                      "text-destructive",
                    item.days_until_stockout !== null &&
                      item.days_until_stockout >= 3 &&
                      item.days_until_stockout < 7 &&
                      "text-warning",
                    (item.days_until_stockout === null || item.days_until_stockout === undefined) &&
                      "text-muted-foreground"
                  )}
                >
                  {item.days_until_stockout !== null
                    ? item.days_until_stockout.toFixed(1)
                    : "∞"}
                </span>
              </td>
              <td className="p-3 text-center">{statusBadge(item.status)}</td>
              <td className="p-3 text-right hidden md:table-cell">
                {formatCurrency(item.stock_value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
