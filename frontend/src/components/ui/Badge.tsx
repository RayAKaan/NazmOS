import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "danger" | "info" | "purple" | "brand";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "bg-bg-tertiary border border-border text-text-secondary",
    success: "bg-status-success/10 text-status-success border border-status-success/30",
    warning: "bg-status-warning/10 text-status-warning border border-status-warning/30",
    danger: "bg-status-error/10 text-status-error border border-status-error/30",
    info: "bg-status-info/10 text-status-info border border-status-info/30",
    purple: "bg-brand-secondary/10 text-brand-secondary border border-brand-secondary/30",
    brand: "bg-brand-primary/10 text-brand-primary border border-brand-primary/30",
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
