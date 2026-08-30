"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * AmbientBackground — slow, low-opacity aurora/mesh motion for brand-forward screens ONLY
 * (Login, Register, Onboarding, Landing hero — §C). Recolored to --brand-gold / --brand-teal
 * at 6–10% opacity; never the library's default indigo/purple palette.
 *
 * One looping ambient per screen max (v3 "what NOT to import": no ambient noise elsewhere).
 * Layered *behind* the existing WeaveTile field.
 *
 * Usage:
 *   <div className="relative"> <AmbientBackground /> <div className="relative">…form…</div> </div>
 */
export function AmbientBackground({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}>
      <motion.div
        className="absolute -top-1/4 -left-1/4 h-[70%] w-[70%] rounded-full blur-[120px]"
        style={{ background: "var(--brand-gold)", opacity: 0.08 }}
        animate={{ x: [0, 60, 0], y: [0, 40, 0] }}
        transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -bottom-1/4 -right-1/4 h-[60%] w-[60%] rounded-full blur-[130px]"
        style={{ background: "var(--brand-teal)", opacity: 0.07 }}
        animate={{ x: [0, -50, 0], y: [0, -30, 0] }}
        transition={{ duration: 26, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
