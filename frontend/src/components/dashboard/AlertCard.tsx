import { AlertTriangle, AlertCircle, Info, CheckCircle, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Alert } from "@/types/dashboard";

interface AlertCardProps {
  alert: Alert;
  onAction?: () => void;
}

export function AlertCard({ alert, onAction }: AlertCardProps) {
  const icons = {
    critical: AlertTriangle,
    warning: AlertCircle,
    info: Info,
    success: CheckCircle,
  };

  const Icon = icons[alert.type] || Info;

  const typeStyles = {
    critical: "bg-destructive/5 border-destructive/30 text-destructive",
    warning: "bg-warning/5 border-warning/30 text-warning",
    info: "bg-primary/5 border-primary/30 text-primary",
    success: "bg-success/5 border-success/30 text-success",
  };

  const borderColors = {
    critical: "border-l-destructive",
    warning: "border-l-warning",
    info: "border-l-primary",
    success: "border-l-success",
  };

  return (
    <div
      className={cn(
        "p-4 rounded-lg border border-l-4 bg-surface shadow-elevation-1 transition-colors hover:bg-surface-hover cursor-pointer",
        borderColors[alert.type]
      )}
      onClick={onAction}
    >
      <div className="flex items-start gap-3">
        <div className={cn("p-2 rounded-lg", typeStyles[alert.type])}>
          <Icon className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm mb-1">{alert.title}</h4>
          <p className="text-xs text-text-secondary mb-2">{alert.message}</p>
          {alert.detail && (
            <p className="text-xs text-text-muted mb-2">{alert.detail}</p>
          )}
          {alert.action_text && (
            <div className="flex items-center gap-1 text-xs text-primary font-medium">
              <span>{alert.action_text}</span>
              <ChevronRight className="w-3 h-3" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
