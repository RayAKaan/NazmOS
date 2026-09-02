"use client";

import { useI18n } from "@/lib/i18n";
import { motion } from "framer-motion";
import { NazmosSection, NazmosHeader } from "./section";
import { CountUp } from "@/components/motion/CountUp";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * OutcomeLoop — the compounding loop. Numbers are clearly labelled SAMPLE
 * demonstrations, never claimed results.
 */
export function OutcomeLoop() {
  const { t } = useI18n();
  const c = t.nazmos.outcomes;

  // These are demonstration figures tied to the sample scenario above.
  const metrics = [
    { label: c.metrics.waitingCapital, value: 12.4, prefix: "SAR ", suffix: "k", decimals: 1 },
    { label: c.metrics.days, value: 62, prefix: "", suffix: "", decimals: 0 },
    { label: c.metrics.stockouts, value: 0, prefix: "", suffix: "", decimals: 0 },
  ];

  return (
    <NazmosSection id="outcomes" className="border-t border-border/60">
      <NazmosHeader badge={c.badge} title={c.title} lead={c.body} />

      <div className="mt-16 grid gap-8 lg:grid-cols-[1.2fr_1fr]">
        <div className="grid gap-4 sm:grid-cols-3">
          {metrics.map((m, i) => (
            <motion.div
              key={m.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08, duration: 0.5, ease: EASE_STANDARD }}
              className="rounded-xl border border-border bg-card p-6"
            >
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
                {m.label}
              </span>
              <div className="mt-3 font-serif text-3xl font-medium tabular-nums text-foreground md:text-4xl">
                <CountUp
                  to={m.value}
                  prefix={m.prefix}
                  suffix={m.suffix}
                  duration={2}
                  formatter={(n) =>
                    n.toLocaleString(undefined, {
                      minimumFractionDigits: m.decimals,
                      maximumFractionDigits: m.decimals,
                    })
                  }
                />
              </div>
            </motion.div>
          ))}
        </div>

        <div className="rounded-xl border border-brand-gold/50 bg-brand-gold/[0.05] p-7">
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-gold/40 bg-brand-gold/[0.08] px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-wider text-foreground">
            {c.sample}
          </span>
          <p className="mt-5 text-sm leading-relaxed text-muted-foreground">{c.demoNote}</p>
        </div>
      </div>
    </NazmosSection>
  );
}
