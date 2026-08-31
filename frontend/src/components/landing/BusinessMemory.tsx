"use client";

import { Brain, ShieldCheck, CheckCircle2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section, SectionLabel } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

export function BusinessMemory() {
  const { t } = useI18n();
  const points = t.landing.businessMemory.points as string[];

  return (
    <Section className="bg-muted/30">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <Reveal>
          <SectionLabel>{t.landing.businessMemory.badge}</SectionLabel>
          <h2 className="mt-5 font-serif text-4xl font-black leading-tight tracking-[-0.02em] text-foreground md:text-5xl">
            {t.landing.businessMemory.title}
          </h2>
          <p className="mt-6 text-lg leading-8 text-muted-foreground">{t.landing.businessMemory.body}</p>
        </Reveal>

        <Reveal delay={0.1}>
          <div className="rounded-3xl border border-border bg-card p-8 shadow-elevation-2">
            <div className="mb-6 flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
                <Brain className="h-6 w-6 text-primary" aria-hidden="true" />
              </span>
              <div>
                <p className="font-serif text-xl font-black text-foreground">NazmOS</p>
                <p className="text-sm text-muted-foreground">Designed to learn from outcomes</p>
              </div>
            </div>
            <ul className="space-y-4">
              {points.map((p) => (
                <li key={p} className="flex items-start gap-3 text-muted-foreground">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
                  <span>{p}</span>
                </li>
              ))}
            </ul>
            <div className="mt-6 flex items-start gap-3 rounded-2xl border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
              <span>
                Autonomy is off by default. Nazm prepares recovery actions; you approve them before anything changes.
              </span>
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}
