import { cn, formatCurrency, formatPercent } from "@/lib/utils";

interface KPICardProps {
  title: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  prefix?: string;
  accentColor?: "blue" | "green" | "yellow" | "purple";
  icon?: React.ReactNode;
}

export function KPICard({
  title,
  value,
  change,
  changeLabel,
  prefix = "",
  accentColor = "blue",
  icon,
}: KPICardProps) {
  const accentBorderColors = {
    blue: "border-l-primary",
    green: "border-l-success",
    yellow: "border-l-warning",
    purple: "border-l-accent-purple",
  };

  return (
    <div
      className={cn(
        "p-5 rounded-xl bg-surface border border-border border-l-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-border/80",
        accentBorderColors[accentColor]
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </span>
        {icon && <div className="text-muted-foreground">{icon}</div>}
      </div>
      <p className="text-2xl md:text-3xl font-bold mb-1">
        {prefix}
        {typeof value === "number" ? (
          value >= 1000 ? (
            <span className="text-foreground">﷼ {value.toLocaleString("ar-SA", { maximumFractionDigits: 0 })}</span>
          ) : (
            value.toLocaleString("ar-SA")
          )
        ) : (
          value
        )}
      </p>
      {change !== undefined && (
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-sm font-medium px-2 py-0.5 rounded",
              change >= 0
                ? "bg-success/10 text-success"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {change >= 0 ? "↑" : "↓"} {formatPercent(Math.abs(change))}
          </span>
          {changeLabel && (
            <span className="text-xs text-muted-foreground">{changeLabel}</span>
          )}
        </div>
      )}
    </div>
  );
}
