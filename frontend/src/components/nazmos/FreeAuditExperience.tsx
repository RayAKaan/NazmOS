"use client";

import { useI18n } from "@/lib/i18n";
import { GuestAuditUploader } from "@/components/landing/GuestAuditUploader";
import { NazmosSection } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * FreeAuditExperience — the conversion section on the product page.
 * Live backend audit, no signup. Names three honest inputs and explains
 * the report.
 */
export function FreeAuditExperience() {
  const { t } = useI18n();
  const c = t.nazmos.freeAudit;

  return (
    <NazmosSection id="free-audit" className="border-t border-border/60">
      <div className="mx-auto max-w-3xl text-center">
        <ScrollReveal>
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-primary">
            {c.badge}
          </span>
          <h2 className="mt-5 font-serif text-3xl font-normal leading-tight text-foreground md:text-5xl text-balance">
            {c.title}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-base text-muted-foreground md:text-lg">
            {c.body}
          </p>
        </ScrollReveal>
      </div>
      <ScrollReveal delay={0.1} className="mt-12">
        <GuestAuditUploader />
      </ScrollReveal>
    </NazmosSection>
  );
}
