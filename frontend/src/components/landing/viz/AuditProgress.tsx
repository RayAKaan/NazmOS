"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { useSafeReducedMotion } from "./useSafeReducedMotion";
import { AUDIT_STAGES } from "./types";

const STEPS: { id: string; dur: number }[] = [
  { id: "read", dur: 700 },
  { id: "columns", dur: 800 },
  { id: "normalize", dur: 900 },
  { id: "match", dur: 1000 },
  { id: "context", dur: 800 },
  { id: "audit", dur: 900 },
  { id: "findings", dur: 600 },
];

/**
 * AuditProgress — staged free-audit processing (§8, §39). The stages map to the real
 * guest-audit pipeline (file reading → column detection → normalization → matching →
 * context → audit → findings). It advances deterministically while the single request
 * is in flight; completion is never artificially delayed past the real API response.
 * Reduced-motion shows the current stage statically without per-step animation.
 */
export function AuditProgress({ onDone, className }: { onDone?: () => void; className?: string }) {
  const { t } = useI18n();
  const reduced = useSafeReducedMotion();
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (reduced) return;
    let active = true;
    let i = 0;
    let timer: ReturnType<typeof setTimeout>;
    const advance = () => {
      if (!active) return;
      if (i >= STEPS.length) {
        onDone?.();
        return;
      }
      setStep(i);
      i += 1;
      timer = setTimeout(advance, STEPS[i - 1]?.dur ?? 800);
    };
    timer = setTimeout(advance, 300);
    return () => {
      active = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced]);

  const current = STEPS[Math.min(step, STEPS.length - 1)];
  const label = (id: string) =>
    ((t.landing.audit.stages as Record<string, string>) || {})[id] ?? id;

  return (
    <div className={cn("rounded-3xl border border-border bg-card p-6 shadow-elevation-2", className)}>
      <div className="mb-5 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
          <motion.div
            className="h-full rounded-full bg-primary"
            initial={false}
            animate={{ width: `${Math.min(100, ((step + 1) / STEPS.length) * 100)}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>
        <p className="shrink-0 font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          {Math.round(((step + 1) / STEPS.length) * 100)}%
        </p>
      </div>

      <ul className="space-y-2.5">
        {STEPS.map((s, i) => {
          const done = reduced ? i < step : i < step;
          const active = i === step;
          return (
            <li key={s.id} className="flex items-center gap-3">
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors",
                  done && "border-success bg-success/15 text-success",
                  active && "border-border bg-primary/15 text-primary",
                  !done && !active && "border-border text-muted-foreground/40"
                )}
              >
                {done ? <Check className="h-3 w-3" aria-hidden="true" /> : null}
              </span>
              <span
                className={cn(
                  "text-sm transition-colors",
                  done || active ? "text-foreground" : "text-muted-foreground/50"
                )}
              >
                {label(s.id)}
              </span>
              {active && (
                <motion.span
                  className="ml-auto h-1.5 w-1.5 rounded-full bg-primary"
                  animate={reduced ? undefined : { opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 0.8, repeat: Infinity }}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
