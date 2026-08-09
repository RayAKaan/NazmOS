"use client";

import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GradientTextProps {
  children: ReactNode;
  className?: string;
  from?: string;
  via?: string;
  to?: string;
}

export function GradientText({
  children,
  className,
  from = "var(--brand-gold)",
  via = "var(--brand-amber)",
  to = "var(--brand-teal)",
}: GradientTextProps) {
  return (
    <span
      className={cn(
        "bg-gradient-to-r from-brand-gold via-brand-amber to-brand-teal bg-clip-text text-transparent",
        className
      )}
      style={{
        backgroundImage: `linear-gradient(135deg, ${from}, ${via}, ${to})`,
      }}
    >
      {children}
    </span>
  );
}
