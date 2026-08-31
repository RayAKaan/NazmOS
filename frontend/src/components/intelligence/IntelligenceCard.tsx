"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Sparkles, Lightbulb, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { SourceChips } from "./SourceChips";

export interface IntelligenceCardProps {
  title?: string;
  summary: string;
  confidence?: number | null;
  sources?: string[];
  icon?: React.ReactNode;
  variant?: "default" | "inline" | "compact";
  actionLabel?: string;
  actionDisabled?: boolean;
  onAction?: () => void;
  onDismiss?: () => void;
  onExplain?: () => void;
  children?: React.ReactNode;
  className?: string;
}

export function IntelligenceCard({
  title = "Nazm Insight",
  summary,
  confidence,
  sources = [],
  icon,
  variant = "default",
  actionLabel,
  actionDisabled,
  onAction,
  onDismiss,
  onExplain,
  children,
  className,
}: IntelligenceCardProps) {
  const [expanded, setExpanded] = useState(false);

  const isCompact = variant === "compact";
  const isInline = variant === "inline";

  return (
    <div
      className={cn(
        "relative overflow-hidden border transition-all",
        isInline
          ? "rounded-xl bg-card border-border"
          : "rounded-2xl bg-gradient-to-br from-intelligence-surface/60 to-card border-intelligence-border shadow-glow-teal",
        className
      )}
    >
      {!isInline && (
        <div className="absolute top-0 right-0 w-32 h-32 bg-brand-teal/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
      )}

      <div className={cn("relative", isCompact ? "p-4" : "p-5 md:p-6")}>
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "shrink-0 flex items-center justify-center rounded-lg",
              isInline
                ? "w-8 h-8 bg-brand-teal/10 text-brand-teal"
                : "w-10 h-10 bg-brand-teal/15 text-brand-teal-light"
            )}
          >
            {icon || <Sparkles className="w-5 h-5" />}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className={cn("font-semibold", isCompact ? "text-sm" : "text-base")}>
                {title}
              </h3>
              {typeof confidence === "number" && (
                <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-mono text-brand-teal-light bg-brand-teal/10 px-2 py-0.5 rounded">
                  {Math.round(confidence * 100)}% confidence
                </span>
              )}
            </div>

            <p className={cn("mt-1 text-muted-foreground", isCompact ? "text-xs" : "text-sm leading-6")}>
              {summary}
            </p>

            {sources.length > 0 && (
              <div className="mt-3">
                <SourceChips sources={sources} />
              </div>
            )}
          </div>

          {(onDismiss || children) && (
            <div className="flex items-center gap-1 shrink-0">
              {children && (
                <button
                  onClick={() => setExpanded((v) => !v)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-brand-cream/5 transition-colors"
                  aria-expanded={expanded}
                  aria-label={expanded ? "Collapse explanation" : "Expand explanation"}
                >
                  {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              )}
              {onDismiss && (
                <button
                  onClick={onDismiss}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                  aria-label="Dismiss insight"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          )}
        </div>

        {expanded && children && (
          <div className="mt-4 pt-4 border-t border-brand-cream/5 animate-in fade-in slide-in-from-top-2">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-brand-teal-light mb-2">
              <Lightbulb className="w-3.5 h-3.5" />
              Reasoning & sources
            </div>
            {children}
          </div>
        )}

        {(onAction || onExplain) && (
          <div className="mt-4 flex flex-wrap gap-2">
            {onAction && actionLabel && (
              <button
                onClick={onAction}
                disabled={actionDisabled}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-teal px-3 py-2 text-sm font-semibold text-brand-night hover:bg-brand-teal-light disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {actionLabel}
              </button>
            )}
            {onExplain && (
              <button
                onClick={onExplain}
                className="inline-flex items-center gap-2 rounded-lg border border-brand-cream/10 px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-brand-cream/5 transition-colors"
              >
                Why this?
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
