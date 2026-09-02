"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * AgentNetwork — specialist agents operating over shared business context.
 *
 * NAZMOS at the top, six specialists below, all feeding into SHARED CONTEXT
 * which resolves to a DECISION. Emphasizes that agents do NOT act
 * independently — the shared context and the decision gate sit between them
 * and any action. Compliance & procurement appear here too.
 */
export function AgentNetwork() {
  const { t } = useI18n();
  const list = t.nazmos.agents.list;

  const agents = [
    { id: "inventory", label: list.inventory, active: true },
    { id: "pricing", label: list.pricing, active: true },
    { id: "supplier", label: list.supplier, active: false },
    { id: "finance", label: list.finance, active: true },
    { id: "compliance", label: list.compliance, active: false },
    { id: "recovery", label: list.recovery, active: true },
    { id: "procurement", label: list.procurement, active: false },
    { id: "margin", label: list.margin, active: true },
  ];

  return (
    <div className="mx-auto w-full max-w-3xl">
      {/* NAZMOS root */}
      <NodeRow label={t.company.hero.denominator} tone="ivory" />

      <Connector />

      {/* Agents grid */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {agents.map((a, i) => (
          <motion.div
            key={a.id}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.4, delay: (i % 4) * 0.06, ease: EASE_STANDARD }}
            className={cn(
              "rounded-lg border px-3 py-2.5 text-center font-mono text-[11px] font-semibold uppercase tracking-wider",
              a.active
                ? "border-primary/40 bg-primary/10 text-foreground"
                : "border-border bg-card/50 text-muted-foreground"
            )}
          >
            {a.label}
          </motion.div>
        ))}
      </div>

      <div className="my-3 flex justify-center" aria-hidden="true">
        <div className="h-6 w-px bg-primary/30" />
      </div>

      {/* Shared context */}
      <NodeRow label={t.nazmos.agents.shared} tone="teal" />

      <div className="my-3 flex justify-center" aria-hidden="true">
        <div className="h-6 w-px bg-primary/30" />
      </div>

      {/* Decision */}
      <NodeRow label={t.nazmos.agents.decision} tone="gold" />

      <p className="mt-6 text-center font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
        {t.nazmos.agents.note}
      </p>
    </div>
  );
}

function NodeRow({ label, tone }: { label: string; tone: "ivory" | "teal" | "gold" }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.94 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, ease: EASE_STANDARD }}
      className="flex justify-center"
    >
      <span
        className={cn(
          "inline-flex items-center gap-2 rounded-full border px-5 py-2.5 font-mono text-sm font-bold uppercase tracking-wide",
          tone === "gold"
            ? "border-brand-gold/50 bg-brand-gold/[0.08] text-foreground"
            : tone === "teal"
            ? "border-primary/40 bg-primary/10 text-foreground"
            : "border-border bg-card text-foreground shadow-subtle"
        )}
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            tone === "gold" ? "bg-brand-gold" : tone === "teal" ? "bg-primary" : "bg-foreground"
          )}
          aria-hidden="true"
        />
        {label}
      </span>
    </motion.div>
  );
}

function Connector() {
  return (
    <div className="my-3 flex justify-center" aria-hidden="true">
      <div className="h-6 w-px bg-primary/30" />
    </div>
  );
}
