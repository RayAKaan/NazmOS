"use client";

import { Plug, FileSpreadsheet, MessageCircle, Store, Cloud } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section, SectionLabel } from "@/components/landing/section";
import { Reveal } from "@/components/landing/Reveal";
import { cn } from "@/lib/utils";

const ICONS = [Store, Store, MessageCircle, Cloud] as const;

export function Integrations() {
  const { t } = useI18n();
  const items = t.landing.integrations.items as string[];

  return (
    <Section>
      <div className="grid items-start gap-12 lg:grid-cols-[0.9fr_1.1fr]">
        <Reveal>
          <SectionLabel>{t.landing.integrations.badge}</SectionLabel>
          <h2 className="mt-5 font-serif text-4xl font-black leading-tight tracking-[-0.02em] text-foreground md:text-5xl">
            {t.landing.integrations.title}
          </h2>
          <p className="mt-6 text-lg leading-8 text-muted-foreground">{t.landing.integrations.body}</p>
          <p className="mt-4 inline-flex items-start gap-2 rounded-2xl border border-warning/30 bg-warning/5 p-3 text-sm text-muted-foreground">
            <Plug className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
            {t.landing.integrations.note}
          </p>
        </Reveal>

        <Reveal delay={0.1}>
          <ul className="grid gap-3 sm:grid-cols-2">
            {items.map((name, i) => {
              const Icon = ICONS[i % ICONS.length];
              return (
                <li
                  key={name}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border border-border bg-card px-5 py-4 shadow-elevation-1"
                  )}
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted">
                    <Icon className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                  </span>
                  <span className="font-semibold text-foreground">{name}</span>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-xs text-muted-foreground">
            <FileSpreadsheet className="mr-1 inline h-4 w-4" aria-hidden="true" />
            Source files audited in our own codebase — see the integration audit.
          </p>
        </Reveal>
      </div>
    </Section>
  );
}
