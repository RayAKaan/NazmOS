"use client";

import { UploadCloud, Link2, FileSearch, CheckCircle2, BarChart3 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

const ICONS = [UploadCloud, Link2, FileSearch, CheckCircle2, BarChart3] as const;

export function HowItWorks() {
  const { t } = useI18n();
  const steps = t.landing.how.steps as { title: string; detail: string }[];

  return (
    <Section id="how-it-works">
      <div className="max-w-3xl">
        <Reveal>
          <h2 className="mt-5 font-serif text-3xl font-bold leading-tight tracking-[-0.02em] text-foreground md:text-4xl">
            {t.landing.how.title}
          </h2>
        </Reveal>
      </div>

      <ol className="mt-14 space-y-4">
        {steps.map((step, i) => {
          const Icon = ICONS[i % ICONS.length];
          return (
            <li key={step.title} className="list-none">
              <Reveal delay={i * 0.05}>
                <div className="relative flex gap-5 rounded-3xl border border-border bg-card p-6 shadow-elevation-1 md:p-8">
                  <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10 sm:flex">
                    <Icon className="h-6 w-6 text-primary" aria-hidden="true" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm font-bold text-primary">0{i + 1}</span>
                      <h3 className="font-serif text-2xl font-black text-foreground">{step.title}</h3>
                    </div>
                    <p className="mt-2 max-w-2xl leading-7 text-muted-foreground">{step.detail}</p>
                  </div>
                </div>
              </Reveal>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}
