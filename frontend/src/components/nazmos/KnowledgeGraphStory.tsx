"use client";

import { useI18n } from "@/lib/i18n";
import { NazmosSection, NazmosHeader } from "./section";
import { BusinessGraph } from "@/components/visualization/BusinessGraph";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * KnowledgeGraphStory — the connected-relations section.
 * The knowledge graph IS the evidence of how business objects relate.
 */
export function KnowledgeGraphStory() {
  const { t } = useI18n();
  const c = t.nazmos.graphStory;

  return (
    <NazmosSection id="graph" className="border-t border-border/60">
      <div className="grid items-center gap-12 lg:grid-cols-[1.1fr_1fr]">
        <ScrollReveal className="order-2 lg:order-1">
          <BusinessGraph />
        </ScrollReveal>
        <div className="order-1 lg:order-2">
          <NazmosHeader badge={c.badge} title={c.title} lead={c.body} />
          <ScrollReveal delay={0.15}>
            <ul className="mt-8 space-y-2.5">
              {(c.points as string[]).map((p, i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-muted-foreground">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                  <span>{p}</span>
                </li>
              ))}
            </ul>
            <p className="mt-6 font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
              {c.note}
            </p>
          </ScrollReveal>
        </div>
      </div>
    </NazmosSection>
  );
}
