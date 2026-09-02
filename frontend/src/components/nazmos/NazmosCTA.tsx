"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { NazmosSection } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * NazmosCTA — closes the product narrative. Returns to the Free Audit or
 * to Nazmak as the parent company. No fabricated claims.
 */
export function NazmosCTA() {
  const { t } = useI18n();
  const c = t.nazmos.cta;

  return (
    <NazmosSection className="border-t border-border/60">
      <ScrollReveal>
        <div className="rounded-2xl border border-border bg-card/40 px-6 py-14 text-center md:px-12">
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-primary">
            {c.badge}
          </span>
          <h2 className="mx-auto mt-5 max-w-2xl font-serif text-3xl font-normal leading-tight text-foreground md:text-5xl text-balance">
            {c.title}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-muted-foreground">{c.body}</p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="#free-audit"
              className="rounded-full px-6 py-3 text-sm font-semibold text-foreground ring-1 ring-inset ring-brand-gold/60 transition-colors hover:bg-brand-gold/[0.08]"
            >
              {c.start}
            </Link>
            <span className="text-xs text-muted-foreground">{c.or}</span>
            <Link href="/" className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
              {c.company}
            </Link>
          </div>
        </div>
      </ScrollReveal>
    </NazmosSection>
  );
}
