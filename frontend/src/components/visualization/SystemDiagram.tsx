"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * SystemDiagram — the deterministic + AI operating model.
 *
 * Data → Deterministic analysis → AI reasoning (when useful) → Validation →
 * Recommendation → Approval → Action. Emphasizes that AI is bounded and the
 * deterministic layer stays authoritative.
 */
export function SystemDiagram() {
  const { t } = useI18n();
  const f = t.nazmos.reasoning.flow;

  const stages = [
    { label: f.data, tone: "neutral", ai: false },
    { label: f.deterministic, tone: "teal", ai: false },
    { label: f.ai, tone: "muted", ai: true },
    { label: f.validation, tone: "teal", ai: false },
    { label: f.decision, tone: "teal", ai: false },
    { label: f.approval, tone: "gold", ai: false },
    { label: f.action, tone: "gold", ai: false },
  ];

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="space-y-1.5">
        {stages.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, x: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08, ease: EASE_STANDARD }}
            className="flex items-center gap-3"
          >
            <span
              className={cn(
                "inline-flex flex-1 items-center justify-between rounded-lg border px-4 py-3",
                s.tone === "gold"
                  ? "border-brand-gold/50 bg-brand-gold/[0.06]"
                  : s.tone === "teal"
                  ? "border-primary/35 bg-primary/5"
                  : s.tone === "muted"
                  ? "border-border bg-card/50"
                  : "border-border bg-card"
              )}
            >
              <span className="font-mono text-sm font-semibold tracking-tight text-foreground">
                {s.label}
              </span>
              {s.ai && (
                <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                  when useful
                </span>
              )}
            </span>
          </motion.div>
        ))}
      </div>

      <p className="mt-6 text-center font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
        {t.nazmos.reasoning.note}
      </p>
    </div>
  );
}
