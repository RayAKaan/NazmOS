"use client";

import { useI18n } from "@/lib/i18n";
import { GuestAuditUploader } from "@/components/landing/GuestAuditUploader";
import { NazmakSection } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * NazmakFreeAudit — the Free Audit conversion widget on the company page.
 * Reuses the existing live guest-audit uploader (connects to the backend).
 */
export function NazmakFreeAudit() {
  const { t } = useI18n();

  return (
    <NazmakSection id="free-audit" className="border-t border-border/60">
      <div className="mx-auto max-w-3xl text-center">
        <ScrollReveal>
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-primary">
            {t.nazmos.freeAudit.badge}
          </span>
          <h2 className="mt-5 font-serif text-3xl font-normal leading-tight text-foreground md:text-5xl text-balance">
            {t.nazmos.freeAudit.title}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-base text-muted-foreground md:text-lg">
            {t.nazmos.freeAudit.body}
          </p>
        </ScrollReveal>
      </div>
      <div className="mt-12">
        <GuestAuditUploader />
      </div>
    </NazmakSection>
  );
}
