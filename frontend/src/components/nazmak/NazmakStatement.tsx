"use client";

import { useI18n } from "@/lib/i18n";
import { ArrowRight, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { NazmakSection } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";
import { track } from "@/lib/analytics";

/**
 * NazmakStatement — the closing editorial statement, leading to the product
 * and to the Free Audit (the primary public conversion).
 */
export function NazmakStatement() {
  const { t, dir } = useI18n();
  const c = t.company.statement;
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  return (
    <NazmakSection id="statement" className="relative overflow-hidden border-t border-border/60">
      <ScrollReveal className="mx-auto max-w-3xl text-center">
        <h2 className="font-serif text-3xl font-normal leading-tight tracking-tight text-foreground md:text-5xl text-balance">
          {c.title}
        </h2>
        <p className="mt-5 font-serif text-xl text-muted-foreground md:text-2xl">
          {c.body}
        </p>

        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/products/nazmos"
            onClick={() => track("home.statement.explore", {})}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-7 py-3.5 font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {c.ctaSecondary} <Arrow className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>

        {/* Free Audit anchor target */}
        <a
          href="#free-audit"
          className="mt-6 inline-block text-sm font-semibold text-primary hover:underline"
        >
          {c.cta}
        </a>
      </ScrollReveal>
    </NazmakSection>
  );
}
