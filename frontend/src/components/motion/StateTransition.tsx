"use client";

import { motion, AnimatePresence } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * StateTransition — animates between system states (idle → processing →
 * result). Each state change is a fade+slide that preserves continuity and
 * communicates a live transformation rather than a static swap.
 */
export function StateTransition({
  state,
  children,
  className,
}: {
  state: string | number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={state}
        className={cn("min-w-0", className)}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.3, ease: EASE }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
