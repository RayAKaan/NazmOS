"use client";

import { useId } from "react";
import { ChevronDown } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section, SectionLabel } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";
import { cn } from "@/lib/utils";

interface Qa {
  q: string;
  a: string;
}

export function FAQ() {
  const { t } = useI18n();
  const items = t.landing.faq.items as Qa[];
  const uid = useId();

  return (
    <Section id="faq" className="bg-muted/30">
      <div className="mx-auto max-w-3xl">
        <Reveal className="text-center">
          <SectionLabel className="justify-center">{t.landing.faq.badge}</SectionLabel>
          <h2 className="mt-5 font-serif text-4xl font-black leading-tight tracking-[-0.02em] text-foreground md:text-5xl">
            {t.landing.faq.title}
          </h2>
        </Reveal>

        <Reveal className="mt-10">
          <div className="space-y-3">
            {items.map((item, i) => {
              const id = `${uid}-${i}`;
              return (
                <details
                  key={item.q}
                  className="group rounded-2xl border border-border bg-card shadow-elevation-1"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-left text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <span>{item.q}</span>
                    <ChevronDown
                      className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
                      aria-hidden="true"
                    />
                  </summary>
                  <div className="px-5 pb-5">
                    <p id={id} className="text-sm leading-7 text-muted-foreground">
                      {item.a}
                    </p>
                  </div>
                </details>
              );
            })}
          </div>
        </Reveal>
      </div>
    </Section>
  );
}
