"use client";

import { motion } from "framer-motion";

export const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * GraphConnection — an animated SVG edge between two graph nodes.
 *
 * Draws the relationship line when in view, then supports an optional
 * highlight state (e.g. when the user hovers/selects a connected node).
 * Color defaults to teal (relationship/intelligence layer); gold when
 * emphasized as a decision/value edge.
 */
export function GraphConnection({
  x1,
  y1,
  x2,
  y2,
  color = "var(--brand-teal)",
  emphasized = false,
  duration = 1.2,
  className,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color?: string;
  emphasized?: boolean;
  duration?: number;
  className?: string;
}) {
  return (
    <motion.line
      className={className}
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={emphasized ? "var(--brand-gold)" : color}
      strokeWidth={emphasized ? 2 : 1.2}
      strokeOpacity={emphasized ? 0.9 : 0.35}
      initial={{ pathLength: 0, opacity: 0 }}
      whileInView={{ pathLength: 1, opacity: 1 }}
      viewport={{ once: true }}
      transition={{ duration, ease: EASE }}
      animate={{
        opacity: emphasized ? 0.9 : 0.35,
        strokeWidth: emphasized ? 2 : 1.2,
      }}
    />
  );
}
