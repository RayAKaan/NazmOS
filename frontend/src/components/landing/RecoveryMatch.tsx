"use client";

import { Store, CheckCircle2, ArrowLeftRight } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

/**
 * RecoveryMatch — Pass 3 trust moment, in brand-teal (its only home on the page).
 *
 * Frame honest copy as a concept, not a claim: two labelled store tiles exchange
 * surplus against shortage, with no invented customer names anywhere. The existing
 * "Product truth" points ride along beneath as the factual strip.
 */
export function RecoveryMatch() {
  const { t } = useI18n();
  const points = t.landing.trust.points as string[];

  return (
    <Section className="overflow-hidden">
      <div className="mx-auto max-w-3xl text-center">
        <Reveal>
          <h2 className="font-serif text-3xl leading-[0.95] tracking-[-0.02em] md:text-5xl">
            <span className="font-extralight text-brand-teal">{t.landing.match.hLead} </span>
            <span className="font-black text-foreground">{t.landing.match.hBold}</span>
          </h2>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">
            {t.landing.match.body}
          </p>
        </Reveal>
      </div>

      <div className="mt-14">
        <Reveal>
          <div className="rounded-3xl border border-brand-teal/30 bg-gradient-to-br from-brand-teal/20 via-brand-teal-dark/10 to-background p-6 shadow-elevation-1 md:p-10">
            <div className="grid items-center gap-5 md:grid-cols-[1fr_auto_1fr]">
              <div className="flex items-center gap-4 rounded-2xl border border-border bg-card/80 p-5 backdrop-blur">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-teal/15">
                  <Store className="h-6 w-6 text-brand-teal" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="font-serif text-xl font-black text-foreground">{t.landing.match.fromLabel}</p>
                  <p className="mt-0.5 text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
                    {t.landing.match.fromDetail}
                  </p>
                </div>
              </div>

              <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-brand-teal/40 bg-background/60 px-4 py-2.5 text-sm font-bold tabular-nums text-brand-teal backdrop-blur">
                <ArrowLeftRight className="h-4 w-4" aria-hidden="true" />
                {t.landing.match.arcNote}
              </div>

              <div className="flex items-center gap-4 rounded-2xl border border-border bg-card/80 p-5 backdrop-blur">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-teal/15">
                  <Store className="h-6 w-6 text-brand-teal" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="font-serif text-xl font-black text-foreground">{t.landing.match.toLabel}</p>
                  <p className="mt-0.5 text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
                    {t.landing.match.toDetail}
                  </p>
                </div>
              </div>
            </div>

            <p className="mt-8 text-sm leading-7 text-muted-foreground [overflow-wrap:anywhere]">
              {t.landing.match.concept}
            </p>
            <p className="mt-2 text-xs uppercase tracking-[0.18em] text-brand-teal/70">
              {t.landing.match.sampleNote}
            </p>

            <ul className="mt-8 grid gap-3 border-t border-brand-teal/20 pt-6 text-sm text-muted-foreground sm:grid-cols-3">
              {points.map((p) => (
                <li key={p} className="flex items-start gap-2 leading-6 [overflow-wrap:anywhere]">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-teal" aria-hidden="true" />
                  {p}
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}