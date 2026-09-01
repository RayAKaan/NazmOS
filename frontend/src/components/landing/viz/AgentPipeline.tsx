"use client";

import { motion } from "framer-motion";
import { Network } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { useSafeReducedMotion } from "./useSafeReducedMotion";
import type { AgentState } from "./types";

/**
 * AgentPipeline — dynamic specialization (§11). A finding enters the analysis router;
 * only the agents relevant to that finding activate and feed a recommendation. Shows
 * that NazmOS never needs every specialist for every problem.
 */
export function AgentPipeline({ agents, className }: { agents: AgentState[]; className?: string }) {
  const reduced = useSafeReducedMotion();
  const { t } = useI18n();
  return (
    <div className={cn("rounded-3xl border border-border bg-card p-6 shadow-elevation-2", className)}>
      <div className="flex items-center gap-2">
        <Network className="h-4 w-4 text-primary" aria-hidden="true" />
        <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">{t.landing.labels.analysisRouter}</p>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {agents.map((a, i) => (
          <motion.div
            key={a.id}
            initial={reduced ? undefined : { opacity: 0, y: 8 }}
            whileInView={reduced ? undefined : { opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08, duration: 0.4 }}
            className={cn(
              "rounded-2xl border p-3 transition-colors",
              a.active
                ? "border-border bg-primary/[0.07]"
                : "border-border bg-muted/20 opacity-50"
            )}
          >
            <div className="flex items-center gap-2">
              <span
                className={cn("h-2 w-2 rounded-full", a.active ? "bg-primary" : "bg-muted-foreground/40")}
                aria-hidden="true"
              />
              <p className={cn("text-sm font-semibold", a.active ? "text-foreground" : "text-muted-foreground")}>
                {a.role}
              </p>
            </div>
            <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
              {a.active ? a.reason : t.landing.labels.idle}
            </p>
          </motion.div>
        ))}
      </div>

      <p className="mt-5 text-center font-mono text-[11px] uppercase tracking-[0.3em] text-muted-foreground">
        {t.landing.labels.specialists
          .replace("{active}", String(agents.filter((a) => a.active).length))
          .replace("{total}", String(agents.length))}
      </p>
    </div>
  );
}
