import { Badge } from "@/components/ui/Badge";

interface StockStatusBadgeProps {
  status: "critical" | "low" | "healthy" | "overstock" | "dead";
}

export function StockStatusBadge({ status }: StockStatusBadgeProps) {
  const variants: Record<string, "danger" | "warning" | "success" | "purple" | "default"> = {
    critical: "danger",
    low: "warning",
    healthy: "success",
    overstock: "purple",
    dead: "default",
  };

  const labels: Record<string, string> = {
    critical: "Critical",
    low: "Low Stock",
    healthy: "Healthy",
    overstock: "Overstock",
    dead: "Dead Stock",
  };

  return <Badge variant={variants[status]}>{labels[status]}</Badge>;
}
