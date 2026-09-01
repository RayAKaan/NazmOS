"use client";

import { useI18n } from "@/lib/i18n";
import { Section } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";
import { FeaturedPlate } from "@/components/landing/viz/FeaturedPlate";

/**
 * Problem — "Four ways stores lose money, quietly."
 *
 * Asymmetric editorial break from the 4-up card grid (Pass 3): one large, red,
 * image-backed `01 Cash leakage` tile (the money moment) with three deliberately
 * quieter supporting rows (Stockouts · Margin · Branch). The red treatment appears
 * exactly once on the page — this is its only home.
 */
export function Problem() {
  const { t } = useI18n();
  const featured = t.landing.problem.featured;
  const items = t.landing.problem.items as { stat: string; detail: string }[];
  const quiet = [items[0], items[2], items[3]];

  return (
    <Section id="product" className="bg-muted/30">
      <div className="max-w-3xl">
        <Reveal>
          <h2 className="font-serif text-3xl leading-[0.95] tracking-[-0.02em] md:text-5xl">
            <span className="font-extralight text-muted-foreground">{t.landing.problem.hLead} </span>
            <span className="font-black text-foreground">{t.landing.problem.hBold} </span>
            <span className="font-extralight text-muted-foreground">{t.landing.problem.hTail}</span>
          </h2>
        </Reveal>
      </div>

      <div className="mt-12 grid gap-4 md:auto-rows-[minmax(0,1fr)] md:grid-cols-3">
        <Reveal className="min-w-0 md:col-span-2 md:row-span-2">
          <div className="relative flex h-full min-h-[440px] flex-col justify-end overflow-hidden rounded-3xl border border-brand-red/30 bg-brand-night p-7 shadow-elevation-2 md:p-9">
            <FeaturedPlate />
            <span className="absolute right-5 top-5 rounded-full border border-brand-red/40 bg-brand-red/15 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-brand-red-light backdrop-blur">
              Sample
            </span>
            <div className="relative">
              <p className="font-mono text-sm font-bold tracking-[0.2em] text-brand-red-light">
                {featured.numeral}
              </p>
              <h3 className="mt-3 max-w-md font-serif text-3xl font-black leading-tight text-brand-cream md:text-5xl">
                {featured.name}
              </h3>
              <p className="mt-3 max-w-md text-sm leading-6 text-brand-cream/70">{featured.caption}</p>
              <div className="mt-7 inline-flex items-baseline gap-2 rounded-2xl border border-brand-cream/15 bg-brand-cream/[0.07] px-4 py-3 backdrop-blur">
                <span className="font-serif text-2xl font-black tabular-nums text-brand-cream md:text-3xl">
                  {featured.figure}
                </span>
                <span className="text-xs text-brand-cream/60">{featured.figureLabel}</span>
              </div>
              <p className="mt-3 text-[11px] uppercase tracking-[0.18em] text-brand-cream/45">
                {featured.figureNote}
              </p>
            </div>
          </div>
        </Reveal>

        {quiet.map((item, i) => {
          const n = [2, 3, 4][i];
          return (
            <Reveal key={item.stat} delay={i * 0.05} className="min-w-0">
              <div className="flex h-full items-start gap-4 rounded-3xl border border-border bg-card px-5 py-6 shadow-elevation-1">
                <span className="pt-1 font-mono text-xs text-muted-foreground/60">0{n}</span>
                <div className="min-w-0 [overflow-wrap:anywhere]">
                  <h3 className="font-serif text-xl font-bold leading-snug text-foreground">{item.stat}</h3>
                  <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{item.detail}</p>
                </div>
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