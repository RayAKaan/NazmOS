"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Target, TrendingUp, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface Decision {
  id: string;
  title: string;
  description?: string | null;
  action_type: string;
  priority: number;
  recoverable_low_sar?: number | null;
  recoverable_high_sar?: number | null;
  expected_recovery_sar?: number | null;
  recovery_confidence?: string;
  evidence?: Record<string, unknown>;
  status: string;
}

interface TopDecisionsProps {
  decisions: Decision[];
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  className?: string;
}

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return `SAR ${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function confidenceColor(confidence?: string) {
  if (confidence === "HIGH") return "text-brand-green bg-brand-green/10";
  if (confidence === "MEDIUM") return "text-brand-amber bg-brand-amber/10";
  return "text-brand-cream/60 bg-brand-cream/10";
}

function ActionIcon({ type }: { type: string }) {
  if (type === "discount") return <AlertTriangle className="h-4 w-4" />;
  if (type === "reorder") return <TrendingUp className="h-4 w-4" />;
  return <Target className="h-4 w-4" />;
}

export function TopDecisions({ decisions, onApprove, onReject, className }: TopDecisionsProps) {
  const top3 = decisions
    .filter((d) => d.status === "suggested")
    .sort((a, b) => a.priority - b.priority)
    .slice(0, 3);

  if (top3.length === 0) return null;

  return (
    <section className={cn("rounded-3xl border border-border bg-surface p-6", className)}>
      <h2 className="text-2xl font-bold">What Deserves Your Attention</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Top {top3.length} decisions ranked by priority and financial impact.
      </p>

      <div className="mt-6 space-y-4">
        {top3.map((decision, idx) => (
          <DecisionCard
            key={decision.id}
            decision={decision}
            rank={idx + 1}
            onApprove={onApprove}
            onReject={onReject}
          />
        ))}
      </div>
    </section>
  );
}

function DecisionCard({
  decision,
  rank,
  onApprove,
  onReject,
}: {
  decision: Decision;
  rank: number;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const evidence = decision.evidence || {};

  const recoveryRange =
    decision.expected_recovery_sar != null
      ? money(decision.expected_recovery_sar)
      : `${money(decision.recoverable_low_sar)}–${money(decision.recoverable_high_sar)}`;

  return (
    <div className="rounded-2xl border border-border bg-brand-night/5 p-5 transition-all hover:shadow-md">
      <div className="flex items-start gap-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-amber/20 text-sm font-bold text-brand-amber">
          {rank}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <ActionIcon type={decision.action_type} />
                <h3 className="text-lg font-bold text-foreground">{decision.title}</h3>
              </div>
              {decision.description && (
                <p className="mt-1 text-sm text-muted-foreground">{decision.description}</p>
              )}
            </div>
            <div className="text-right">
              <div className="text-lg font-bold text-brand-green">{recoveryRange}</div>
              <span className={cn("inline-block rounded-full px-2 py-0.5 text-xs font-bold", confidenceColor(decision.recovery_confidence))}>
                {decision.recovery_confidence}
              </span>
            </div>
          </div>

          {/* Why section */}
          <div className="mt-3 rounded-xl bg-brand-night/10 p-3">
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Why</p>
            <p className="mt-1 text-sm text-foreground">
              {decision.action_type === "discount" && "This item has low or no recent sales. Capital is locked in inventory that is not generating revenue."}
              {decision.action_type === "reorder" && "This item is selling well and may face a stockout. Reordering preserves revenue."}
              {decision.action_type === "recovery_match" && "This item has excess inventory beyond 30-day demand. Consider matching with a buyer."}
              {decision.action_type === "margin_fix" && "Current margin is below target. Review pricing to recover profit opportunity."}
              {decision.action_type === "DO_NOTHING" && "No action is recommended at this time."}
            </p>
          </div>

          {/* Expand evidence */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-3 flex items-center gap-1 text-xs font-bold text-muted-foreground hover:text-foreground"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {expanded ? "Hide evidence" : "Show evidence"}
          </button>

          {expanded && (
            <div className="mt-2 rounded-xl bg-brand-night/10 p-3 text-xs text-muted-foreground">
              <div className="grid gap-2 sm:grid-cols-2">
                {Object.entries(evidence).map(([key, value]) => (
                  <div key={key}>
                    <span className="font-bold text-foreground">{key.replace(/_/g, " ")}:</span>{" "}
                    {typeof value === "number" ? value.toLocaleString() : String(value ?? "—")}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          {decision.status === "suggested" && (onApprove || onReject) && (
            <div className="mt-4 flex gap-3">
              {onApprove && (
                <button
                  onClick={() => onApprove(decision.id)}
                  className="rounded-xl bg-brand-green px-4 py-2 text-sm font-bold text-brand-night hover:bg-brand-green/90"
                >
                  Approve
                </button>
              )}
              {onReject && (
                <button
                  onClick={() => onReject(decision.id)}
                  className="rounded-xl border border-brand-cream/20 px-4 py-2 text-sm font-bold text-muted-foreground hover:bg-brand-cream/5"
                >
                  Reject
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
