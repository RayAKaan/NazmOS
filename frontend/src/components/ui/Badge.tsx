import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "danger" | "info" | "purple" | "brand";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "bg-muted border border-border text-muted-foreground",
    success: "bg-success/10 text-success border border-success/30",
    warning: "bg-warning/10 text-warning border border-warning/30",
    danger: "bg-destructive/10 text-destructive border border-destructive/30",
    info: "bg-status-info/10 text-status-info border border-status-info/30",
    purple: "bg-accent-purple/10 text-accent-purple border border-accent-purple/30",
    brand: "bg-primary/10 text-primary border border-primary/30",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}

export function StatusBadge({ status }: { status: "critical" | "low" | "healthy" | "overstock" | "dead" }) {
  const statusConfig = {
    critical: { variant: "danger" as const, label: "Critical" },
    low: { variant: "warning" as const, label: "Low" },
    healthy: { variant: "success" as const, label: "Healthy" },
    overstock: { variant: "purple" as const, label: "Overstock" },
    dead: { variant: "default" as const, label: "Dead Stock" },
  };

  const config = statusConfig[status];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
