"use client";

import { Brain, ShieldCheck, CheckCircle2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";
import { logoMark } from "@/components/landing/logo";

/**
 * BusinessMemory — Pass 3: one company, one continuous panel.
 *
 * Nazmak and NazmOS share a single gold-bleeding surface (no two bordered boxes
 * arguing they are unrelated). Weight-contrast headline (#3 of 3): light "Built by"
 * over black "Nazmak". The gold mark crosses the split — the logo glow is the seam.
 */
export function BusinessMemory() {
  const { t } = useI18n();
  const points = t.landing.businessMemory.points as string[];

  return (
    <Section className="bg-muted/30">
      <Reveal>
        <div className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-elevation-2 md:p-12">
          <div className="relative grid gap-10 md:grid-cols-2 md:gap-12">
            <div className="min-w-0 [overflow-wrap:anywhere]">
              <div className="flex items-center gap-3">
                <logoMark.Svg className="h-10 w-10 shrink-0" />
                <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-muted-foreground">
                  {t.landing.businessMemory.badge}
                </p>
              </div>
              <h2 className="mt-5 font-serif text-3xl leading-[1.02] tracking-[-0.02em] md:text-4xl">
                <span className="font-extralight text-muted-foreground">{t.landing.businessMemory.companyLead} </span>
                <span className="font-black text-foreground">{t.landing.businessMemory.companyBold}</span>
                <span className="font-extralight text-muted-foreground"> {t.landing.businessMemory.companyTail}</span>
              </h2>
              <p className="mt-4 font-serif text-xl font-bold leading-snug text-primary">
                {t.landing.businessMemory.sub}
              </p>
              <p className="mt-6 text-lg leading-8 text-muted-foreground">{t.landing.businessMemory.body}</p>
            </div>

            <div className="min-w-0 [overflow-wrap:anywhere]">
              <div className="mb-5 flex items-center gap-3">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10">
                  <Brain className="h-6 w-6 text-primary" aria-hidden="true" />
                </span>
                <div>
                  <p className="font-serif text-xl font-black text-foreground">NazmOS</p>
                  <p className="text-sm text-muted-foreground">{t.landing.businessMemory.title}</p>
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
          </div>

          {/* Gold mark beam crossing the split — the one-company seam. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-1/2 top-1/2 h-[130%] w-px -translate-x-1/2 -translate-y-1/2 bg-gradient-to-b from-transparent via-brand-gold/45 to-transparent"
          />
        </div>
      </Reveal>
    </Section>
  );
}