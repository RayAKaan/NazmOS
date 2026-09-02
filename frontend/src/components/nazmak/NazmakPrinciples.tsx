"use client";

import { useI18n } from "@/lib/i18n";
import { ShieldCheck, Scale, EyeOff } from "lucide-react";
import { NazmakSection, NazmakHeader } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * NazmakPrinciples — trust through transparency and product truth.
 * Evidence before claims. No fake customers, logos, or numbers.
 */
export function NazmakPrinciples() {
  const { t } = useI18n();
  const c = t.company.principles;

  const points = [
    { icon: ShieldCheck, text: c.points[0] as string },
    { icon: Scale, text: c.points[1] as string },
    { icon: EyeOff, text: c.points[2] as string },
  ];

  return (
    <NazmakSection id="principles" className="border-t border-border/60">
      <NazmakHeader badge={c.badge} title={c.title} lead={c.body} />

      <div className="mt-14 grid gap-6 md:grid-cols-3">
        {points.map((p, i) => {
          const Icon = p.icon;
          return (
            <ScrollReveal key={i} delay={i * 0.08}>
              <div className="flex h-full gap-4 rounded-lg border border-border bg-card p-6">
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                  <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
                </span>
                <p className="text-sm leading-relaxed text-muted-foreground">{p.text}</p>
              </div>
            </ScrollReveal>
          );
        })}
      </div>
    </NazmakSection>
  );
}
