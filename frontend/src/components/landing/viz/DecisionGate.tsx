"use client";

import { Check, ShieldCheck, ShieldX } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import type { DecisionState } from "./types";

/**
 * DecisionGate — the deterministic decision boundary (§13). A recommendation only
 * advances once every check (evidence, constraints, financial, risk) passes. Renders
 * as a trustworthy, technical receipt rather than a magic "AI" verdict.
 */
export function DecisionGate({
  decision,
  className,
}: {
  decision: DecisionState;
  className?: string;
}) {
  const { t } = useI18n();
  const gated = decision.checks.every((c) => c.pass);
  return (
    <div className={cn("overflow-hidden rounded-3xl border border-border bg-card shadow-elevation-2", className)}>
      <div className="border-b border-border px-6 py-5">
        <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">{t.landing.labels.recommendation}</p>
        <p className="mt-1 font-serif text-2xl font-black text-foreground">
          {decision.title} · {decision.from} → {decision.to}
        </p>
      </div>

      <div className="space-y-3 px-6 py-5">
        <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">{t.landing.labels.decisionGate}</p>
        {decision.checks.map((c) => (
          <div key={c.label} className="flex items-start gap-3">
            <span
              className={cn(
                "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                c.pass ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive"
              )}
            >
              {c.pass ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <ShieldX className="h-3.5 w-3.5" aria-hidden="true" />}
            </span>
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">{c.label}</p>
              <p className="text-xs text-muted-foreground">{c.detail}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-6 py-4">
        <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-muted-foreground">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          {gated ? t.landing.labels.allChecksPassed : t.landing.labels.blocked}
        </div>
        <span
          className={cn(
            "rounded-full px-3 py-1 font-mono text-xs font-bold uppercase tracking-wider",
            gated ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive"
          )}
        >
          {gated ? t.landing.labels.approve : t.landing.labels.reject}
        </span>
      </div>
    </div>
  );
}
