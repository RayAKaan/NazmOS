import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * SeamBorder — Kintsugi (gold repair) container. §1: ONLY Money Audit & Recovery Match
 * ever render this. A loss-state → recovered-state transition draws a single gold seam
 * once (600ms, ease-out, never loops — §2.4 `--duration-seam`).
 *
 * States:
 *   idle      → no seam
 *   resolving → subtle dashed outline (in progress)
 *   recovered → gold seam drawn once via `animate-seam-reveal`
 *
 * Usage:
 *   <SeamBorder state={match.status === "completed" ? "recovered" : "resolving"}>
 *     ...card content...
 *   </SeamBorder>
 */
export type SeamState = "idle" | "resolving" | "recovered";
export type SeamBorderProps = {
  state: SeamState;
  children: ReactNode;
  className?: string;
};

export function SeamBorder({ state, children, className }: SeamBorderProps) {
  const recovered = state === "recovered";
  const resolving = state === "resolving";

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border bg-card",
        recovered ? "border-primary/40" : "border-border",
        resolving && "border-dashed border-secondary/60",
        className
      )}
    >
      {children}

      {recovered && (
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          fill="none"
        >
          {/* single gold thread across the top edge, drawn once */}
          <path
            d="M 0 1.5 L 100 1.5"
            pathLength={1}
            stroke="var(--primary)"
            strokeWidth={1.5}
            strokeDasharray="1"
            strokeDashoffset="1"
            className="animate-seam-reveal"
          />
        </svg>
      )}
    </div>
  );
}
