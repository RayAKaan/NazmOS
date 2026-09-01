"use client";

import Link from "next/link";
import { CheckCircle2, Info } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section, SectionLabel } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

interface Plan {
  name: string;
  price: string;
  body: string;
  features: string[];
}

export function Pricing() {
  const { t } = useI18n();
  const cards = t.landing.pricing.cards as Plan[];

  return (
    <Section id="pricing">
      <div className="mx-auto max-w-3xl text-center">
        <Reveal>
          <SectionLabel className="justify-center">{t.landing.pricing.badge}</SectionLabel>
          <h2 className="mt-5 font-serif text-3xl font-bold leading-tight tracking-[-0.02em] text-foreground md:text-4xl">
            {t.landing.pricing.title}
          </h2>
        </Reveal>
      </div>

      <div className="mt-12 grid gap-5 lg:grid-cols-3">
        {cards.map((plan, i) => {
          const highlight = i === 1;
          return (
            <Reveal key={plan.name} delay={i * 0.08}>
              <div
                className={
                  highlight
                    ? "relative flex h-full flex-col rounded-3xl border border-brand-amber/60 bg-card p-7 shadow-elevation-1 shadow-glow-lg"
                    : "flex h-full flex-col rounded-3xl border border-border bg-card p-7 shadow-elevation-1"
                }
              >
                <h3 className="font-serif text-2xl font-bold text-foreground">{plan.name}</h3>
                <p className="mt-4 font-serif text-3xl font-black text-primary tabular-nums">{plan.price}</p>
                <p className="mt-3 leading-7 text-muted-foreground">{plan.body}</p>
                <ul className="mt-6 flex-1 space-y-2">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-foreground/80">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  href="/register?intent=free-audit"
                  className={
                    highlight
                      ? "mt-8 inline-flex items-center justify-center rounded-xl bg-brand-amber px-5 py-3 text-sm font-bold text-brand-night transition-colors hover:bg-brand-amber/90"
                      : "mt-8 inline-flex items-center justify-center rounded-xl bg-primary px-5 py-3 text-sm font-bold text-primary-foreground transition-colors hover:bg-primary/90"
                  }
                >
                  {t.landing.nav.getStarted}
                </Link>
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal className="mt-8">
        <p className="mx-auto flex max-w-3xl items-start justify-center gap-2 text-sm text-muted-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          {t.landing.pricing.note}
        </p>
      </Reveal>
    </Section>
  );
}
