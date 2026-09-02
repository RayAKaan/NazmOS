"use client";

import { useI18n } from "@/lib/i18n";
import { NazmosSection, NazmosHeader } from "./section";
import { DataConvergence } from "@/components/visualization/DataConvergence";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * DataStory — the Data section of the product page.
 * Fragmented business inputs animate together into the system.
 */
export function DataStory() {
  const { t } = useI18n();
  const c = t.nazmos.dataStory;

  return (
    <NazmosSection id="data" className="border-t border-border/60">
      <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.1fr]">
        <div>
          <NazmosHeader badge={c.badge} title={c.title} lead={c.body} />
          <ScrollReveal delay={0.15}>
            <ul className="mt-8 space-y-2.5">
              {[
                c.examples.sales,
                c.examples.inventory,
                c.examples.supplier,
                c.examples.finance,
                c.examples.manual,
              ].map((item, i) => (
                <li key={i} className="flex items-center gap-3 text-sm text-muted-foreground">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
            <p className="mt-6 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
              {c.note}
            </p>
          </ScrollReveal>
        </div>
        <ScrollReveal delay={0.1} className="flex justify-center lg:justify-end">
          <DataConvergence />
        </ScrollReveal>
      </div>
    </NazmosSection>
  );
}
