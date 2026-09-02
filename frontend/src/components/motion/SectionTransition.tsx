"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * SectionTransition — a quiet connector that keeps visual continuity between
 * sections. Renders a thin rule with an optional centered node that draws in,
 * implying the system continues across the page boundary. Prevents abrupt
 * section edges and ties the page to one continuous machine.
 */
export function SectionTransition({
  children,
  className,
  tone = "border",
}: {
  children?: ReactNode;
  className?: string;
  tone?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <motion.div
        aria-hidden="true"
        className={cn("h-px w-full", tone)}
        initial={{ scaleX: 0, opacity: 0 }}
        whileInView={{ scaleX: 1, opacity: 1 }}
        viewport={{ once: true, margin: "-40px" }}
        transition={{ duration: 1.2, ease: EASE }}
      />
      {children && <div className="relative">{children}</div>}
    </div>
  );
}
