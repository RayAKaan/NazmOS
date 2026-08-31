"use client";

import { WalletCards, Store, TrendingUp, Activity } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section, SectionLabel } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

const ICONS = [WalletCards, Store, TrendingUp, Activity] as const;

export function Problem() {
  const { t } = useI18n();
  const items = t.landing.problem.items as { stat: string; detail: string }[];

  return (
    <Section id="product" className="bg-muted/30">
      <div className="max-w-3xl">
        <Reveal>
          <SectionLabel>{t.landing.problem.badge}</SectionLabel>
          <h2 className="mt-5 font-serif text-4xl font-black leading-tight tracking-[-0.02em] text-foreground md:text-6xl">
            {t.landing.problem.title}
          </h2>
        </Reveal>
      </div>

      <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {items.map((item, i) => {
          const Icon = ICONS[i % ICONS.length];
          return (
            <Reveal key={item.stat} delay={i * 0.06}>
              <div className="group h-full rounded-3xl border border-border bg-card p-6 shadow-elevation-1 transition-all hover:-translate-y-0.5 hover:shadow-elevation-2">
                <div className="mb-8 flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground/60">0{i + 1}</span>
                  <Icon className="h-5 w-5 text-primary opacity-70" aria-hidden="true" />
                </div>
                <h3 className="font-serif text-2xl font-black text-foreground">{item.stat}</h3>
                <p className="mt-3 leading-7 text-muted-foreground">{item.detail}</p>
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal className="mt-16">
        <p className="max-w-3xl font-serif text-2xl font-bold leading-snug text-foreground md:text-3xl">
          {t.landing.problem.transition}
        </p>
      </Reveal>
    </Section>
  );
}
