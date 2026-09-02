"use client";

import { useI18n } from "@/lib/i18n";
import { NazmosSection, NazmosHeader } from "./section";
import { AgentNetwork } from "@/components/visualization/AgentNetwork";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * AgentSystem — specialist agents over shared context.
 */
export function AgentSystem() {
  const { t } = useI18n();
  const c = t.nazmos.agents;

  return (
    <NazmosSection id="agents" className="border-t border-border/60">
      <NazmosHeader badge={c.badge} title={c.title} lead={c.body} className="mx-auto text-center" />

      <ScrollReveal delay={0.1} className="mt-16">
        <AgentNetwork />
      </ScrollReveal>
    </NazmosSection>
  );
}
