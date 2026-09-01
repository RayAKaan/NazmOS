"use client";

import { motion } from "framer-motion";

/**
 * FlowLine — a directional data stream along an SVG path.
 *
 * Renders a base path plus a dashed overlay whose dash offset travels forward,
 * communicating "data moving toward a stage" (§25, §26 system animations).
 * Respects prefers-reduced-motion: when reduced, the base path is static and no
 * traveling pulse is drawn. Pure SVG, GPU-friendly (CSS transform / dash-offset).
 */
export function FlowLine({
  d,
  className,
  duration = 1.6,
  strokeWidth = 1.5,
  arrowId,
}: {
  /** SVG path `d` string. */
  d: string;
  className?: string;
  duration?: number;
  strokeWidth?: number;
  /** Optional marker-end reference (e.g. "url(#flow-arrow)") — pass the id portion. */
  arrowId?: string;
}) {
  return (
    <g className={className}>
      <motion.path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        className="text-foreground/20"
        initial={false}
      />
      <motion.path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        className="text-primary/70"
        strokeDasharray="3 9"
        initial={{ strokeDashoffset: 0 }}
        animate={{ strokeDashoffset: -48 }}
        transition={{ duration, repeat: Infinity, ease: "linear" }}
        style={undefined}
      />
    </g>
  );
}

export function FlowArrowDef({ id = "flow-arrow" }: { id?: string }) {
  return (
    <defs>
      <marker
        id={id}
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerWidth="6"
        markerHeight="6"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
      </marker>
    </defs>
  );
}
