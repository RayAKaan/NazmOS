"use client";

import { ShieldCheck, Scale, EyeOff, Lock } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section, SectionLabel } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

const ICONS = [ShieldCheck, Scale, EyeOff] as const;

export function Trust() {
  const { t } = useI18n();
  const points = t.landing.trust.points as string[];

  return (
    <Section id="trust" className="bg-muted/30">
      <div className="mx-auto max-w-3xl text-center">
        <Reveal>
          <SectionLabel className="justify-center">{t.landing.trust.badge}</SectionLabel>
          <h2 className="mt-5 font-serif text-4xl font-black leading-tight tracking-[-0.02em] text-foreground md:text-5xl">
            {t.landing.trust.title}
          </h2>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">
            {t.landing.trust.body}
          </p>
        </Reveal>
      </div>

      <div className="mt-12 grid gap-4 md:grid-cols-3">
        {points.map((p, i) => {
          const Icon = ICONS[i % ICONS.length];
          return (
            <Reveal key={p} delay={i * 0.06}>
              <div className="h-full rounded-3xl border border-border bg-card p-6 shadow-elevation-1">
                <Icon className="mb-4 h-6 w-6 text-primary" aria-hidden="true" />
                <p className="leading-7 text-foreground">{p}</p>
              </div>
            </Reveal>
          );
        })}
      </div>

      <div className="mt-12 flex flex-wrap items-center justify-center gap-3 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Lock className="h-4 w-4 text-success" aria-hidden="true" /> No customer data
        </span>
      </div>
    </Section>
  );
}
