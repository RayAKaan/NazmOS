import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Section({
  id,
  className,
  children,
}: {
  id?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className={cn("px-5 py-20 md:px-8 md:py-28", className)}>
      <div className="mx-auto max-w-7xl">{children}</div>
    </section>
  );
}

export function SectionLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <span className="h-px w-8 bg-primary/60" />
      <span className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-muted-foreground">
        {children}
      </span>
    </span>
  );
}
