"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * DataConvergence — the Data Story visualization.
 * Fragmented business inputs (CSV, inventory, POS, supplier, financial)
 * begin isolated, then converge into the NazmOS system core.
 * Meaningful data paths, not a particle field.
 */
export function DataConvergence() {
  const { t } = useI18n();
  const src = t.nazmos.hero.sources;

  const sources = [
    { id: "csv", label: src.csv, x: 8, y: 18 },
    { id: "inventory", label: src.inventory, x: 80, y: 14 },
    { id: "pos", label: src.pos, x: 88, y: 58 },
    { id: "supplier", label: src.supplier, x: 12, y: 70 },
    { id: "financial", label: src.financial, x: 46, y: 10 },
  ];

  return (
    <div className="relative aspect-square w-full max-w-[420px]">
      {/* Converging lines */}
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {sources.map((s, i) => (
          <motion.line
            key={s.id}
            x1={s.x} y1={s.y} x2="50" y2="50"
            stroke="var(--brand-teal)"
            strokeOpacity="0.35"
            strokeWidth="0.4"
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.9, delay: 0.4 + i * 0.12, ease: "easeInOut" }}
          />
        ))}
      </svg>

      {/* Center: NazmOS */}
      <motion.div
        className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2"
        initial={{ scale: 0 }}
        whileInView={{ scale: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6, delay: 1.0, ease: EASE_STANDARD }}
      >
        <motion.div
          animate={{ boxShadow: ["0 0 30px color-mix(in oklch, var(--brand-teal) 30%, transparent)", "0 0 50px color-mix(in oklch, var(--brand-teal) 40%, transparent)", "0 0 30px color-mix(in oklch, var(--brand-teal) 30%, transparent)"] }}
          transition={{ duration: 5, repeat: Infinity }}
          className="flex h-24 w-24 items-center justify-center rounded-full border border-primary/40 bg-card"
        >
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-primary">
            {t.company.hero.denominator}
          </span>
        </motion.div>
      </motion.div>

      {/* Converging sources */}
      {sources.map((s, i) => (
        <motion.div
          key={s.id}
          className="absolute z-10 -translate-x-1/2 -translate-y-1/2"
          style={{ left: `${s.x}%`, top: `${s.y}%` }}
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.1 }}
        >
          <span className="rounded-lg border border-border bg-card px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-foreground shadow-subtle">
            {s.label}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
