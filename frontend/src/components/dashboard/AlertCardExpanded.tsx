"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  AlertTriangle,
  Info,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  X,
  Package,
  Clock,
  TrendingDown,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Alert {
  id: string;
  type: "critical" | "warning" | "info" | "success";
  title: string;
  message: string;
  itemName?: string;
  currentStock?: number;
  dailyAvg?: number;
  daysLeft?: number;
  recommendation?: {
    action: string;
    quantity: number;
    unit: string;
    estimatedCost: number;
    leadTime: string;
  };
  createdAt: string;
}

interface AlertCardExpandedProps {
  alert: Alert;
  onDismiss?: () => void;
  onApply?: () => void;
}

export function AlertCardExpanded({ alert, onDismiss, onApply }: AlertCardExpandedProps) {
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const config = {
    critical: {
      icon: AlertCircle,
      bgColor: "bg-status-error/10",
      borderColor: "border-status-error/30",
      accentColor: "border-l-status-error",
      badgeColor: "bg-destructive text-destructive-foreground",
      iconColor: "text-status-error",
    },
    warning: {
      icon: AlertTriangle,
      bgColor: "bg-status-warning/10",
      borderColor: "border-status-warning/30",
      accentColor: "border-l-status-warning",
      badgeColor: "bg-warning text-warning-foreground",
      iconColor: "text-status-warning",
    },
    info: {
      icon: Info,
      bgColor: "bg-status-info/10",
      borderColor: "border-status-info/30",
      accentColor: "border-l-status-info",
      badgeColor: "bg-status-info text-brand-night",
      iconColor: "text-status-info",
    },
    success: {
      icon: CheckCircle,
      bgColor: "bg-status-success/10",
      borderColor: "border-status-success/30",
      accentColor: "border-l-status-success",
      badgeColor: "bg-success text-success-foreground",
      iconColor: "text-status-success",
    },
  };

  const { icon: Icon, bgColor, borderColor, accentColor, badgeColor, iconColor } =
    config[alert.type];

  if (dismissed) return null;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -100 }}
      className={cn(
        "rounded-xl border border-l-[3px] overflow-hidden transition-all",
        bgColor,
        borderColor,
        accentColor
      )}
      data-tour="alerts"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={cn("px-2 py-0.5 rounded text-xs font-semibold uppercase", badgeColor)}>
            {alert.type}
          </span>
          <span className="text-xs text-text-muted">
            {new Date(alert.createdAt).toLocaleTimeString("ar-SA", {
              hour: "numeric",
              minute: "2-digit",
            })}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 rounded-lg hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
            aria-label={expanded ? "Collapse alert details" : "Expand alert details"}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="p-1.5 rounded-lg hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
            aria-label="Dismiss alert"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="px-4 pb-4">
        <div className="flex items-start gap-3">
          <div className={cn("p-2 rounded-lg", bgColor)}>
            <Icon size={20} className={iconColor} />
          </div>

          <div className="flex-1 min-w-0">
            <h4 className="font-semibold text-text-primary mb-1">{alert.title}</h4>
            <p className="text-sm text-text-secondary">{alert.message}</p>

            {alert.currentStock !== undefined && (
              <div className="flex flex-wrap gap-4 mt-3 text-sm">
                <div className="flex items-center gap-1.5 text-text-muted">
                  <Package size={14} />
                  <span>
                    Current:{" "}
                    <span className="text-text-primary font-medium">{alert.currentStock}</span>
                  </span>
                </div>
                {alert.dailyAvg && (
                  <div className="flex items-center gap-1.5 text-text-muted">
                    <TrendingDown size={14} />
                    <span>
                      Daily avg:{" "}
                      <span className="text-text-primary font-medium">{alert.dailyAvg}</span>
                    </span>
                  </div>
                )}
                {alert.daysLeft && (
                  <div className="flex items-center gap-1.5 text-text-muted">
                    <Clock size={14} />
                    <span>
                      Days left:{" "}
                      <span
                        className={cn(
                          "font-medium",
                          alert.daysLeft <= 2 ? "text-status-error" : "text-text-primary"
                        )}
                      >
                        {alert.daysLeft}
                      </span>
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <AnimatePresence>
          {expanded && alert.recommendation && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="mt-4"
            >
              <div className="p-4 rounded-lg bg-bg-tertiary/50 border border-border">
                <div className="flex items-start gap-2 mb-3">
                  <span className="text-lg">📦</span>
                  <div>
                    <h5 className="font-medium text-text-primary">
                      Recommendation: Order {alert.recommendation.quantity}{" "}
                      {alert.recommendation.unit}
                    </h5>
                    <p className="text-sm text-text-muted">
                      Estimated cost: ﷼ {alert.recommendation.estimatedCost.toLocaleString("ar-SA")} ·{" "}
                      Lead time: {alert.recommendation.leadTime}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 mt-4">
                  <button
                    onClick={() => setDismissed(true)}
                    className="px-4 py-2 rounded-lg text-sm text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
                  >
                    Dismiss
                  </button>
                  <button
                    onClick={onApply}
                    className="px-4 py-2 rounded-lg bg-brand-primary text-brand-night text-sm font-medium hover:bg-brand-primary-hover transition-colors"
                  >
                    Apply Restock →
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
