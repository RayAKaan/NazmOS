"use client";

import { useI18n } from "@/lib/i18n";
import { GuestAuditUploader } from "@/components/landing/GuestAuditUploader";
import { Section, SectionLabel } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";

export function FreeAudit() {
  const { t } = useI18n();

  return (
    <Section id="free-audit" className="border-y border-border">
      <div className="mx-auto max-w-3xl text-center">
        <Reveal>
          <SectionLabel className="justify-center">{t.landing.nav.freeAudit}</SectionLabel>
          <h2 className="mt-5 font-serif text-4xl font-black leading-tight tracking-[-0.02em] text-foreground md:text-5xl">
            {t.landing.hero.idle.title}
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-muted-foreground">{t.landing.hero.idle.body}</p>
        </Reveal>
      </div>
      <div className="mt-12">
        <GuestAuditUploader />
      </div>
    </Section>
  );
}
