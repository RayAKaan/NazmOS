"use client";

import { useI18n } from "@/lib/i18n";
import { NazmakSection, NazmakHeader } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";
import { motion } from "framer-motion";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * NazmosHowItWorks — condensed "one machine" flow for the company page.
 * Data → Understanding → Memory → Relationships → Specialists → Decision,
 * drawn as a connected horizontal pipeline that collapses vertically on mobile.
 */
export function NazmosHowItWorks() {
  const { t } = useI18n();
  const c = t.company.howWorks;

  const steps = [
    { title: c.steps.one.title, body: c.steps.one.body },
    { title: c.steps.two.title, body: c.steps.two.body },
    { title: c.steps.three.title, body: c.steps.three.body },
    { title: c.steps.four.title, body: c.steps.four.body },
    { title: c.steps.five.title, body: c.steps.five.body },
    { title: c.steps.six.title, body: c.steps.six.body },
  ];

  return (
    <NazmakSection id="how-works" className="border-t border-border/60">
      <NazmakHeader badge={c.badge} title={c.title} />

      <div className="mt-16 flex items-stretch">
        <div className="grid w-full gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-6">
          {steps.map((s, i) => (
            <motion.div
              key={s.title}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.5, delay: i * 0.06, ease: EASE_STANDARD }}
              className="group relative flex flex-col bg-card p-5 transition-colors hover:bg-muted/40"
            >
              <span className="font-mono text-[10px] font-bold text-primary">
                0{i + 1}
              </span>
              <h3 className="mt-3 font-serif text-base font-medium text-foreground">
                {s.title}
              </h3>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{s.body}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </NazmakSection>
  );
}
