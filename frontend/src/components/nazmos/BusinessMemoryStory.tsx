"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { NazmosSection, NazmosHeader } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * BusinessMemoryStory — accumulated business context.
 * Product/sales/inventory/supplier history + decisions + outcomes →
 * BUSINESS MEMORY → future context.
 */
export function BusinessMemoryStory() {
  const { t } = useI18n();
  const c = t.nazmos.memoryStory;

  const fields = [
    c.fields.product,
    c.fields.sales,
    c.fields.inventory,
    c.fields.supplier,
    c.fields.decisions,
    c.fields.outcomes,
  ];

  return (
    <NazmosSection id="memory">
      <NazmosHeader badge={c.badge} title={c.title} lead={c.body} />

      <div className="mt-16 grid items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
        <MemoryCore fields={fields} becomes={c.becomes} future={c.future} />
        <ScrollReveal delay={0.15}>
          <div className="rounded-xl border border-border bg-card p-7">
            <p className="font-mono text-[11px] font-bold uppercase tracking-widest text-primary">
              {c.badge}
            </p>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              {c.body}
            </p>
          </div>
        </ScrollReveal>
      </div>
    </NazmosSection>
  );
}

function MemoryCore({
  fields,
  becomes,
  future,
}: {
  fields: string[];
  becomes: string;
  future: string;
}) {
  return (
    <div className="mx-auto w-full max-w-xl">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {fields.map((f, i) => (
          <motion.div
            key={f}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.05, duration: 0.4, ease: EASE_STANDARD }}
            className="rounded-md border border-border bg-card px-3 py-2.5 text-center font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
          >
            {f}
          </motion.div>
        ))}
      </div>

      <div className="my-4 flex items-center justify-center gap-3" aria-hidden="true">
        <span className="h-px w-16 bg-primary/40" />
        <span className="font-mono text-[10px] uppercase tracking-wider text-primary">{becomes}</span>
        <span className="h-px w-16 bg-primary/40" />
      </div>

      <motion.div
        initial={{ scale: 0.96, opacity: 0 }}
        whileInView={{ scale: 1, opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, ease: EASE_STANDARD }}
        className="rounded-lg border border-primary/40 bg-primary/5 px-5 py-4 text-center"
      >
        <span className="font-serif text-xl font-medium text-foreground">BUSINESS MEMORY</span>
      </motion.div>

      <div className="my-4 flex justify-center" aria-hidden="true">
        <div className="h-6 w-px bg-primary/30" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, delay: 0.2, ease: EASE_STANDARD }}
        className="rounded-lg border border-brand-gold/50 bg-brand-gold/[0.06] px-4 py-3 text-center font-mono text-sm font-semibold uppercase tracking-wider text-foreground"
      >
        {future}
      </motion.div>
    </div>
  );
}
