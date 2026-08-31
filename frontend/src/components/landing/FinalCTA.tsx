"use client";

import Link from "next/link";
import { ArrowRight, ArrowLeft, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

export function FinalCTA() {
  const { t, dir } = useI18n();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  return (
    <Section>
      <Reveal>
        <div className="rounded-3xl border border-border bg-card p-8 shadow-elevation-2 md:p-12">
          <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-success/10 px-3 py-1.5 text-xs font-bold text-success">
                <ShieldCheck className="h-4 w-4" aria-hidden="true" /> Free tier honesty
              </div>
              <h2 className="font-serif text-3xl font-black leading-tight text-foreground md:text-5xl">
                {t.landing.finalCta.title}
              </h2>
              <p className="mt-4 max-w-3xl text-lg leading-7 text-muted-foreground">{t.landing.finalCta.body}</p>
            </div>
            <Link
              href="/register?intent=free-audit"
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-7 py-4 text-lg font-bold text-primary-foreground shadow-elevation-2 hover:bg-primary/90"
            >
              {t.landing.finalCta.cta} <Arrow className="h-5 w-5" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}
