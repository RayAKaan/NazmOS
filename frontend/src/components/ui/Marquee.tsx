"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * Marquee — continuous horizontal scroll (Magic UI "Marquee" technique, reimplemented on
 * framer-motion). Children are rendered twice in identical columns; the -50% translate
 * loops seamlessly because each column carries its own trailing gap.
 * Used for the landing partner/merchant logo strip (§D).
 *
 * Usage:
 *   <Marquee speed={30} gap={48}>{logos.map((l) => <span key={l}>{l}</span>)}</Marquee>
 */
export function Marquee({
  children,
  speed = 30,
  gap = 48,
  className,
}: {
  children: React.ReactNode;
  /** seconds per full loop — lower = faster. */
  speed?: number;
  /** gap between items in px (also the trailing padding that makes the loop seamless). */
  gap?: number;
  className?: string;
}) {
  return (
    <div className={cn("relative flex w-full overflow-hidden", className)}>
      <motion.div
        className="flex w-max"
        animate={{ x: ["0%", "-50%"] }}
        transition={{ duration: speed, ease: "linear", repeat: Infinity }}
      >
        {[0, 1].map((i) => (
          <div
            key={i}
            aria-hidden={i === 1}
            className="flex shrink-0 items-center"
            style={{ columnGap: gap, paddingRight: gap }}
          >
            {children}
          </div>
        ))}
      </motion.div>
    </div>
  );
}
