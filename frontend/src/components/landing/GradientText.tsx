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
  from = "#6366f1",
  via = "#8b5cf6",
  to = "#06b6d4",
}: GradientTextProps) {
  return (
    <span
      className={cn(
        "bg-gradient-to-r from-brand-primary via-brand-secondary to-brand-accent bg-clip-text text-transparent",
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
