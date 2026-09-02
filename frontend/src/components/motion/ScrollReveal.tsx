"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

export const EASE_STANDARD = [0.22, 1, 0.36, 1] as const;

/**
 * ScrollReveal — a reusable scroll-triggered reveal primitive.
 *
 * Animates content into view once as it enters the viewport. Supports
 * configurable direction, offset, delay, and duration. Respects
 * prefers-reduced-motion via framer-motion's built-in handling (transforms
 * collapse to opacity-only).
 */
export function ScrollReveal({
  children,
  className,
  delay = 0,
  duration = 0.6,
  y = 24,
  x = 0,
  once = true,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  duration?: number;
  y?: number;
  x?: number;
  once?: boolean;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y, x }}
      whileInView={{ opacity: 1, y: 0, x: 0 }}
      viewport={{ once, margin: "-80px" }}
      transition={{ duration, ease: EASE_STANDARD, delay }}
    >
      {children}
    </motion.div>
  );
}
