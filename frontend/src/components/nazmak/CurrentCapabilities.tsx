"use client";

import { useI18n } from "@/lib/i18n";
import { NazmakSection, NazmakHeader } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";
import { cn } from "@/lib/utils";

/**
 * CurrentCapabilities — what Nazmak (via NazmOS) can actually do today.
 * Verified capabilities only, no roadmap. Presented as a single system
 * surface grouped conceptually, not as generic feature cards.
 */
export function CurrentCapabilities() {
  const { t } = useI18n();
  const c = t.company.capabilities;

  const items: { title: string; body: string; group: string }[] = [
    { title: c.items.data.title, body: c.items.data.body, group: "understand" },
    { title: c.items.inventory.title, body: c.items.inventory.body, group: "understand" },
    { title: c.items.finance.title, body: c.items.finance.body, group: "understand" },
    { title: c.items.relationships.title, body: c.items.relationships.body, group: "connect" },
    { title: c.items.memory.title, body: c.items.memory.body, group: "connect" },
    { title: c.items.agents.title, body: c.items.agents.body, group: "connect" },
    { title: c.items.decisions.title, body: c.items.decisions.body, group: "decide" },
    { title: c.items.reasoning.title, body: c.items.reasoning.body, group: "decide" },
    { title: c.items.approval.title, body: c.items.approval.body, group: "decide" },
    { title: c.items.freeAudit.title, body: c.items.freeAudit.body, group: "decide" },
  ];

  return (
    <NazmakSection id="capabilities">
      <NazmakHeader badge={c.badge} title={c.title} lead={c.body} />

      <div className="mt-14 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-5">
        {items.map((item, i) => (
          <ScrollReveal key={item.title} delay={(i % 5) * 0.05} className="h-full">
            <div className="flex h-full flex-col bg-card p-6 transition-colors hover:bg-muted/40">
              <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                {item.body.split(" ").length > 6 ? "system" : item.group}
              </span>
              <h3 className="mt-3 font-serif text-lg font-medium text-foreground">
                {item.title}
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                {item.body}
              </p>
            </div>
          </ScrollReveal>
        ))}
      </div>

      <ScrollReveal delay={0.1}>
        <p className={cn("mt-6 text-xs text-muted-foreground")}>{c.note}</p>
      </ScrollReveal>
    </NazmakSection>
  );
}
