import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * BentoGrid — the single shared KPI-cluster grid (§1 priority 3, §4 contract).
 * One primitive for Dashboard / Ops / Forecast / any KPI screen — never per-page
 * hand-rolled `grid-cols-*` (the step-zero audit's #1 drift target).
 *
 * cols: responsive column count per breakpoint.
 * gap:  §2.1 spacing step (4/6/8/12/16/24 → 16/24/32/48/64/96px).
 *
 * Usage:
 *   <BentoGrid cols={{ base: 1, md: 2, lg: 4 }} gap={6}>
 *     <Card density="editorial">…</Card>
 *   </BentoGrid>
 */

function colClass(n: number): string {
  return ({ 1: "grid-cols-1", 2: "grid-cols-2", 3: "grid-cols-3", 4: "grid-cols-4", 5: "grid-cols-5", 6: "grid-cols-6" } as Record<number, string>)[n] ?? "grid-cols-1";
}

function gapClass(n: number): string {
  return ({ 4: "gap-4", 6: "gap-6", 8: "gap-8", 12: "gap-12", 16: "gap-16", 24: "gap-24" } as Record<number, string>)[n] ?? "gap-6";
}

export type BentoGridProps = {
  cols?: { base: number; md: number; lg: number };
  gap?: 4 | 6 | 8 | 12 | 16 | 24;
  children: ReactNode;
  className?: string;
};

export function BentoGrid({ cols = { base: 1, md: 2, lg: 4 }, gap = 6, children, className }: BentoGridProps) {
  return (
    <div
      className={cn(
        "grid",
        colClass(cols.base),
        `md:${colClass(cols.md)}`,
        `lg:${colClass(cols.lg)}`,
        gapClass(gap),
        className
      )}
    >
      {children}
    </div>
  );
}
