"use client";

import { useI18n } from "@/lib/i18n";
import { NazmosSection, NazmosHeader } from "./section";
import { SystemDiagram } from "@/components/visualization/SystemDiagram";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * ReasoningGate — the deterministic + bounded-AI reasoning section.
 */
export function ReasoningGate() {
  const { t } = useI18n();
  const c = t.nazmos.reasoning;

  return (
    <NazmosSection id="reasoning" className="border-t border-border/60">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <div>
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
        <ScrollReveal delay={0.1}>
          <SystemDiagram />
        </ScrollReveal>
      </div>
    </NazmosSection>
  );
}
