"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * SplitText — one-time word reveal for hero headlines (ReactBits "SplitText" /
 * Aceternity "TextGenerateEffect" technique, reimplemented on the repo's framer-motion).
 * Plays once on mount; never loops. Words rise out of an overflow mask, 8px, staggered.
 *
 * Usage:
 *   <h1><SplitText text="Find the cash trapped inside your store." /></h1>
 */
export function SplitText({
  text,
  className,
  delay = 0,
  stagger = 0.06,
}: {
  text: string;
  className?: string;
  delay?: number;
  stagger?: number;
}) {
  const words = text.split(" ");
  return (
    <span className={cn("inline", className)} aria-label={text}>
      {words.map((word, i) => (
        <span
          key={`${word}-${i}`}
          className="inline-block overflow-hidden align-bottom pb-[0.08em] -mb-[0.08em]"
        >
          <motion.span
            className="inline-block will-change-transform"
            initial={{ y: "110%" }}
            animate={{ y: 0 }}
            transition={{
              duration: 0.6,
              ease: [0.16, 1, 0.3, 1],
              delay: delay + i * stagger,
            }}
          >
            {word}
            {i < words.length - 1 ? "\u00A0" : ""}
          </motion.span>
        </span>
      ))}
    </span>
  );
}
