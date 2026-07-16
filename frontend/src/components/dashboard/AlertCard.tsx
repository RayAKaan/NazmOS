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
    critical: "bg-accent-red/5 border-accent-red/30 text-accent-red",
    warning: "bg-accent-yellow/5 border-accent-yellow/30 text-accent-yellow",
    info: "bg-accent-blue/5 border-accent-blue/30 text-accent-blue",
    success: "bg-accent-green/5 border-accent-green/30 text-accent-green",
  };

  const borderColors = {
    critical: "border-l-accent-red",
    warning: "border-l-accent-yellow",
    info: "border-l-accent-blue",
    success: "border-l-accent-green",
  };

  return (
    <div
      className={cn(
        "p-4 rounded-xl border border-l-4 bg-surface transition-colors hover:bg-surface-hover cursor-pointer",
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
            <div className="flex items-center gap-1 text-xs text-accent-blue font-medium">
              <span>{alert.action_text}</span>
              <ChevronRight className="w-3 h-3" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
