"use client";

import { useI18n } from "@/lib/i18n";
import { NazmakSection, NazmakHeader } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";
import { DataFlow } from "@/components/motion/DataFlow";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * NazmakBuilding — "What Nazmak is building."
 * Presents the core thesis: data becomes context, context becomes memory,
 * memory becomes decisions. Editorial composition with a flowing system
 * motif rather than a card grid.
 */
export function NazmakBuilding() {
  const { t } = useI18n();
  const c = t.company.building;

  const rows: { title: string; body: string; accent?: boolean }[] = [
    { title: c.points.p1.title, body: c.points.p1.body },
    { title: c.points.p2.title, body: c.points.p2.body },
    { title: c.points.p3.title, body: c.points.p3.body, accent: true },
  ];

  return (
    <NazmakSection id="building" className="border-t border-border/60">
      <NazmakHeader badge={c.badge} title={c.title} lead={c.body} />

      <div className="mt-16 grid gap-6 lg:grid-cols-3">
        {rows.map((row, i) => (
          <ScrollReveal key={row.title} delay={i * 0.08}>
            <div
              className={cn(
                "relative h-full rounded-lg border bg-card p-7",
                row.accent ? "border-primary/30" : "border-border"
              )}
            >
              <span
                className={cn(
                  "font-mono text-xs font-bold",
                  row.accent ? "text-brand-gold" : "text-primary"
                )}
              >
                0{i + 1}
              </span>
              <h3 className="mt-4 font-serif text-xl font-medium text-foreground">
                {row.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {row.body}
              </p>
              {i < rows.length - 1 && (
                <div className="pointer-events-none absolute -right-3 top-1/2 hidden h-px w-6 -translate-y-1/2 lg:block" aria-hidden="true" />
              )}
            </div>
          </ScrollReveal>
        ))}
      </div>

      {/* Connecting flow line */}
      <div className="mt-10 hidden lg:block" aria-hidden="true">
        <div className="mx-auto max-w-3xl">
          <DataFlow from={{ x: 6, y: 2 }} to={{ x: 94, y: 2 }} className="h-4 w-full" active />
        </div>
      </div>
    </NazmakSection>
  );
}
