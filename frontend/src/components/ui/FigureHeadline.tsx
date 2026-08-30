"use client";

import { useEffect, useState } from "react";
import NumberFlow from "@number-flow/react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * FigureHeadline — the money figure is a HEADLINE, not a chip (§1 editorial priority).
 *
 * §2.2 + v3 §Typography: ALWAYS --font-sans (Inter), tabular-nums, weight 800 (primary) /
 * 700 (secondary), 4xl/3xl with -0.03em tracking — never serif, never mono. Label above:
 * xs, uppercase, muted, 0.04em tracking.
 *
 * §B + v3: counts up on mount (and on value change) via @number-flow/react — the already
 * installed, previously-unused dependency. No new animation library.
 * §2.6: Intl.NumberFormat is the single formatting path (Western numerals, locale separators).
 *
 * Usage:
 *   <FigureHeadline value={128450} currency="SAR" label="Money recovered" />
 *   <FigureHeadline value={-3120} label="Margin leakage" size="secondary"
 *     trend={{ direction: "down", percent: 2.4 }} />
 */

export type FigureHeadlineProps = {
  value: number;
  currency?: "SAR" | string;
  label: string;
  size?: "primary" | "secondary";
  trend?: { direction: "up" | "down"; percent: number };
  /** Semantic tone for the figure (money-audit / recovery-match). default = foreground. */
  tone?: "default" | "gold" | "success" | "destructive" | "warning";
  className?: string;
};

const toneClass: Record<NonNullable<FigureHeadlineProps["tone"]>, string> = {
  default: "text-foreground",
  gold: "text-primary",
  success: "text-success",
  destructive: "text-destructive",
  warning: "text-warning",
};

export function FigureHeadline({
  value,
  currency = "SAR",
  label,
  size = "primary",
  trend,
  tone = "default",
  className,
}: FigureHeadlineProps) {
  // Count-up on mount + on value change. NumberFlow respects reduced-motion internally.
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const id = setTimeout(() => setDisplay(value), 120);
    return () => clearTimeout(id);
  }, [value]);

  const sizeClass =
    size === "primary" ? "text-4xl font-extrabold" : "text-3xl font-bold";

  return (
    <div className={cn("flex flex-col", className)}>
      <span className="text-xs font-medium uppercase tracking-[0.04em] text-muted-foreground">
        {label}
      </span>

      <div className="mt-1 flex items-baseline gap-2">
        <span
          className={cn(
            "font-sans tabular-nums tracking-[-0.03em]",
            toneClass[tone],
            sizeClass
          )}
        >
          <NumberFlow
            value={display}
            locales="en-SA"
            format={{ maximumFractionDigits: 2 }}
          />
        </span>
        <span className="text-sm text-muted-foreground">{currency}</span>
      </div>

      {trend && (
        <span
          className={cn(
            "mt-1 inline-flex items-center gap-1 text-sm tabular-nums",
            trend.direction === "up" ? "text-success" : "text-destructive"
          )}
        >
          {trend.direction === "up" ? (
            <TrendingUp strokeWidth={1.75} className="h-4 w-4" aria-hidden="true" />
          ) : (
            <TrendingDown strokeWidth={1.75} className="h-4 w-4" aria-hidden="true" />
          )}
          {trend.direction === "up" ? "+" : "\u2212"}
          {trend.percent.toFixed(1)}%
        </span>
      )}
    </div>
  );
}
