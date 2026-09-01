"use client";

import { motion } from "framer-motion";
import { ArrowDown, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { useSafeReducedMotion } from "./useSafeReducedMotion";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import type { OutcomeState } from "./types";

/**
 * OutcomeLoop — the most satisfying beat (§15): APPROVED action → business result →
 * actual outcome → learning returns to business memory, closing the loop. Shows
 * expected vs actual (deterministic sample) and what the system learned.
 */
export function OutcomeLoop({ outcome, className }: { outcome: OutcomeState; className?: string }) {
  const reduced = useSafeReducedMotion();
  const { t } = useI18n();
  return (
    <div className={cn("overflow-hidden rounded-3xl border border-border bg-card shadow-elevation-2", className)}>
      <div className="border-b border-border px-6 py-4">
        <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">{t.landing.labels.fromActionToMemory}</p>
      </div>

      <div className="px-6 py-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-2xl border border-border bg-muted/30 p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t.landing.labels.expectedRecovery}</p>
            <div className="mt-1">
              <FigureHeadline value={outcome.expected} label="" size="secondary" tone="default" currency="SAR" />
            </div>
          </div>
          <div className="rounded-2xl border border-success/25 bg-success/[0.06] p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{t.landing.labels.actualOutcome}</p>
            <div className="mt-1">
              <FigureHeadline value={outcome.actual} label="" size="secondary" tone="success" currency="SAR" />
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-[auto_1fr] items-center gap-2 text-sm">
          <ArrowDown className="h-4 w-4 text-success" aria-hidden="true" />
          <p className="text-foreground">
            <span className="font-semibold">{t.landing.labels.approved}</span> · {t.landing.labels.inventoryTransfer}
          </p>
          <ArrowDown className="h-4 w-4 text-success" aria-hidden="true" />
          <p className="text-foreground">
            <span className="font-semibold">{t.landing.labels.outcomeRecorded}</span> · {t.landing.labels.cashRecovered}
          </p>
        </div>

        <div className="mt-5 flex items-start gap-3 rounded-2xl border border-border bg-primary/[0.06] p-4">
          <RotateCcw className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="text-sm leading-6 text-muted-foreground">{outcome.learned}</p>
        </div>

        <motion.p
          className="mt-4 text-center font-mono text-[11px] uppercase tracking-[0.3em] text-primary"
          animate={reduced ? undefined : { opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          aria-hidden={reduced ? true : undefined}
        >
          ← {t.landing.labels.returnsToMemory}
        </motion.p>
      </div>
    </div>
  );
}
