"use client";

import { motion } from "framer-motion";
import { useId } from "react";

/**
 * DataFlow — an animated data-stream line.
 *
 * A teal pulse of light travelling along an SVG path, representing the flow
 * of business data into the system. Used where a single meaningful data path
 * communicates state change (data moving toward understanding).
 *
 * The line is drawn once via stroke-dashoffset reveal, then a pulsing dot
 * travels to signal active flow. Respects reduced-motion.
 */
export function DataFlow({
  from = { x: 0, y: 0 },
  to = { x: 100, y: 0 },
  duration = 2.4,
  color = "var(--brand-teal)",
  className,
  active = true,
}: {
  from?: { x: number; y: number };
  to?: { x: number; y: number };
  duration?: number;
  color?: string;
  className?: string;
  active?: boolean;
}) {
  const pathId = useId();
  const d = `M ${from.x} ${from.y} L ${to.x} ${to.y}`;

  return (
    <svg
      className={className}
      viewBox="0 0 100 100"
      fill="none"
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={pathId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={color} stopOpacity="0" />
          <stop offset="100%" stopColor={color} stopOpacity="0.6" />
        </linearGradient>
      </defs>

      {/* Static base line */}
      <motion.path
        d={d}
        stroke={color}
        strokeOpacity={0.25}
        strokeWidth={1}
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true }}
        transition={{ duration, ease: "easeInOut" }}
      />

      {/* Travelling data pulse */}
      {active && (
        <motion.circle
          r={2.4}
          fill={color}
          style={{ filter: `drop-shadow(0 0 4px ${color})` }}
          initial={{ offsetDistance: "0%" }}
          animate={{ offsetDistance: "100%" }}
          transition={{
            duration: duration * 1.2,
            repeat: Infinity,
            repeatType: "loop",
            ease: "easeInOut",
          }}
          transform={undefined}
        >
          <animateMotion dur={`${duration * 1.2}s`} repeatCount="indefinite" path={d} />
        </motion.circle>
      )}
    </svg>
  );
}
