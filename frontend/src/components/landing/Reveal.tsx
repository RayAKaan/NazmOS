"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

// Scroll-reveal wrapper (Skiper-style) that rises/clears content into view once.
// Respects reduced-motion via framer-motion's built-in handling; the fade itself is
// subtle and content remains readable even mid-animation. Plays once per element.
export function Reveal({
  children,
  className,
  delay = 0,
  y = 20,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  y?: number;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay }}
    >
      {children}
    </motion.div>
  );
}
