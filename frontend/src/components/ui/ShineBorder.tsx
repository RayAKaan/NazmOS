"use client";

import { useId } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * ShineBorder — a gold beam that travels the element border (Magic UI "BorderBeam" /
 * Aceternity "ShineBorder" technique), reimplemented on the repo's own framer-motion
 * (no new dependency) and recolored to --primary (brand gold). Reserved for PRIMARY CTAs
 * only — same discipline v2 already applies to kintsugi (§B: never every button).
 *
 * Idle cycle ~6s, linear; the beam never loops the *content*, just the border ring.
 *
 * Usage: wrap a primary CTA (must be relative + overflow-hidden is handled here).
 *   <ShineBorder className="rounded-lg">
 *     <button className="bg-primary text-primary-foreground ...">Start free</button>
 *   </ShineBorder>
 */
export function ShineBorder({
  children,
  className,
  duration = 6,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  duration?: number;
  delay?: number;
}) {
  const raw = useId();
  const gradientId = `shine-${raw.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <div className={cn("relative overflow-hidden", className)}>
      {children}
      <svg
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        fill="none"
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style={{ stopColor: "transparent" }} />
            <stop offset="50%" style={{ stopColor: "var(--primary)" }} />
            <stop offset="100%" style={{ stopColor: "transparent" }} />
          </linearGradient>
        </defs>
        <motion.rect
          x="0.6"
          y="0.6"
          width="98.8"
          height="98.8"
          rx="7"
          ry="7"
          stroke={`url(#${gradientId})`}
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeDasharray="25 275"
          initial={{ strokeDashoffset: 0 }}
          animate={{ strokeDashoffset: -300 }}
          transition={{ duration, repeat: Infinity, ease: "linear", delay }}
        />
      </svg>
    </div>
  );
}
