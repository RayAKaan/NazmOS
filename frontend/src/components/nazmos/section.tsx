import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { ScrollReveal } from "@/components/motion/ScrollReveal";

/**
 * NazmosSection — product-page section shell for NazmOS.
 * Uses generous whitespace and a consistent editorial header pattern.
 */
export function NazmosSection({
  id,
  className,
  children,
}: {
  id?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className={cn("scroll-mt-24 px-5 py-16 md:px-8 md:py-24", className)}>
      <div className="mx-auto w-full max-w-7xl">{children}</div>
    </section>
  );
}

export function NazmosHeader({
  badge,
  title,
  lead,
  className,
}: {
  badge?: string;
  title: ReactNode;
  lead?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("max-w-3xl", className)}>
      {badge && (
        <ScrollReveal>
          <span className="inline-flex items-center gap-3">
            <span className="h-px w-8 bg-primary/60" aria-hidden="true" />
            <span className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-muted-foreground">
              {badge}
            </span>
          </span>
        </ScrollReveal>
      )}
      <ScrollReveal delay={0.05}>
        <h2 className="mt-6 font-serif text-3xl font-normal leading-tight tracking-tight text-foreground md:text-5xl text-balance">
          {title}
        </h2>
      </ScrollReveal>
      {lead && (
        <ScrollReveal delay={0.1}>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted-foreground md:text-lg">
            {lead}
          </p>
        </ScrollReveal>
      )}
    </div>
  );
}
