"use client";

import { useI18n } from "@/lib/i18n";
import { NazmosSection, NazmosHeader } from "./section";
import { DecisionCard } from "@/components/visualization/DecisionCard";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * DecisionStory — a concrete, sample decision moment.
 */
export function DecisionStory() {
  const { t } = useI18n();
  const c = t.nazmos.decision;

  return (
    <NazmosSection id="decision" className="border-t border-border/60">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <ScrollReveal className="order-2 lg:order-1 flex justify-center lg:justify-start">
          <DecisionCard />
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
          </ScrollReveal>
        </div>
      </div>
    </NazmosSection>
  );
}
