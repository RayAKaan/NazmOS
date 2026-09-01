"use client";

import { useId } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useSafeReducedMotion } from "./useSafeReducedMotion";
import { SIGNATURE_LOOP } from "./types";

/**
 * SignatureLoop — the NazmOS visual signature (§16): OBSERVE → UNDERSTAND → ANALYZE
 * → RECOMMEND → ACT → MEASURE → LEARN, drawn as a subtle, continuous circular flow.
 *
 * A bright pulse travels around the ring to communicate "the loop closes"; the ring
 * itself stays steady. Reduced motion collapses it to a static ring so meaning is
 * never animation-only (§29). Uses rotation transform only (GPU-friendly).
 */
export function SignatureLoop({ className }: { className?: string }) {
  const gradId = useId();
  const reduced = useSafeReducedMotion();
  const N = SIGNATURE_LOOP.length;
  const R = 46;
  const CX = 50;
  const CY = 50;

  const angleFor = (i: number) => (i / N) * 360 - 90;

  return (
    <div className={cn("relative aspect-square w-full max-w-[360px]", className)}>
      <svg viewBox="0 0 100 100" className="h-full w-full" aria-hidden="true">
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--secondary)" />
            <stop offset="55%" stopColor="var(--primary)" />
            <stop offset="100%" stopColor="var(--success)" />
          </linearGradient>
        </defs>

        {/* Ring */}
        <circle
          cx={CX}
          cy={CY}
          r={R}
          fill="none"
          stroke="var(--border)"
          strokeWidth={0.4}
          strokeDasharray="1 2"
          className="opacity-70"
        />
        <circle
          cx={CX}
          cy={CY}
          r={R - 5}
          fill="none"
          stroke="var(--border)"
          strokeWidth={0.25}
          className="opacity-50"
        />

        {/* Traveling pulse along the ring */}
        {!reduced && (
          <motion.path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 1 1 ${CX + R} ${CY}`}
            fill="none"
            stroke={`url(#${gradId})`}
            strokeWidth={0.6}
            strokeLinecap="round"
            style={{ strokeDasharray: "6 220" }}
            animate={{ strokeDashoffset: -226 }}
            transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
          />
        )}

        {/* Stage labels on ring */}
        {SIGNATURE_LOOP.map((stage, i) => {
          const a = (angleFor(i) * Math.PI) / 180;
          // Round to fixed precision so server and client render identical DOM.
          const x = Math.round((CX + R * Math.cos(a)) * 1000) / 1000;
          const y = Math.round((CY + R * Math.sin(a)) * 1000) / 1000;
          return (
            <g key={stage}>
              <circle cx={x} cy={y} r={1.6} fill="var(--card)" stroke="var(--border)" strokeWidth={0.25} />
              <text x={x} y={y - 3.4} textAnchor="middle" fontSize={2.7} fill="var(--muted-foreground)">
                {stage}
              </text>
            </g>
          );
        })}

        {/* Center mark */}
        <circle cx={CX} cy={CY} r={7} fill="none" stroke="var(--primary)" strokeWidth={0.3} strokeDasharray="1 1.4" />
        <text
          x={CX}
          y={CY + 1.2}
          textAnchor="middle"
          fontSize={3.4}
          fontWeight={800}
          fill="var(--foreground)"
          className="font-serif"
        >
          NazmOS
        </text>
      </svg>
    </div>
  );
}
