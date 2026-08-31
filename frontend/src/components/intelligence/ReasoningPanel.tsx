"use client";

import { CheckCircle2, Goal, ListOrdered } from "lucide-react";
import { cn } from "@/lib/utils";
import { SourceChips } from "./SourceChips";
import type { IntelligenceReasonResponse } from "@/types/intelligence";

interface ReasoningPanelProps {
  response: IntelligenceReasonResponse;
  className?: string;
}

export function ReasoningPanel({ response, className }: ReasoningPanelProps) {
  const { answer, decision, plan, sources } = response;

  return (
    <div className={cn("space-y-4", className)}>
      <div className="prose-intelligence">
        <p className="text-foreground">{answer}</p>
      </div>

      {decision && (
        <div className="rounded-xl border border-intelligence-border bg-intelligence-surface/40 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-brand-teal-light mb-2">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Recommended action
          </div>
          <p className="font-semibold text-foreground">{decision.title || decision.action_type}</p>
          {decision.description && (
            <p className="mt-1 text-sm text-muted-foreground">{decision.description}</p>
          )}
          {typeof decision.confidence === "number" && (
            <p className="mt-2 text-xs font-mono text-brand-teal-light">
              Confidence: {Math.round(decision.confidence * 100)}%
              {typeof decision.expected_value_sar === "number" && (
                <span className="ml-3">Expected value: SAR {decision.expected_value_sar.toLocaleString()}</span>
              )}
            </p>
          )}
        </div>
      )}

      {plan && plan.steps && plan.steps.length > 0 && (
        <div className="rounded-xl border border-intelligence-border bg-intelligence-surface/40 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-brand-teal-light mb-2">
            <Goal className="w-3.5 h-3.5" />
            Plan: {plan.goal}
          </div>
          <ol className="space-y-2">
            {plan.steps.map((step, index) => (
              <li key={index} className="flex items-start gap-2 text-sm text-muted-foreground">
                <ListOrdered className="w-4 h-4 text-brand-teal shrink-0 mt-0.5" />
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {sources && sources.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Sources</div>
          <SourceChips sources={sources} />
        </div>
      )}
    </div>
  );
}
