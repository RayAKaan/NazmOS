"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * NodeActivation — a graph/system node chip that activates on enter.
 *
 * Fades in and scales, then glows in teal or gold when `active`. Used to
 * represent business entities and system nodes that "wake up" as the story
 * progresses, rather than static chips.
 */
export function NodeActivation({
  children,
  className,
  active = false,
  gold = false,
  delay = 0,
  duration = 0.5,
}: {
  children: ReactNode;
  className?: string;
  active?: boolean;
  gold?: boolean;
  delay?: number;
  duration?: number;
}) {
  return (
    <motion.div
      className={cn("relative", className)}
      initial={{ opacity: 0, scale: 0.92 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration, ease: EASE, delay }}
      animate={{
        boxShadow: active
          ? gold
            ? "0 0 24px oklch(78.0% 0.14 82 / 0.35)"
            : "0 0 24px oklch(68.0% 0.11 175 / 0.35)"
          : "0 0 0px transparent",
      }}
    >
      {children}
    </motion.div>
  );
}
