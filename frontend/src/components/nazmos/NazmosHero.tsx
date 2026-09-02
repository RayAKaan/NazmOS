"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * NazmosHero — the product hero.
 *
 * Visual: fragmented business data (CSV/Inventory/POS/Supplier/Financial)
 * becoming connected understanding, becoming a decision. The visualization
 * IS the hero — not a dashboard screenshot.
 */
export function NazmosHero() {
  const { t } = useI18n();
  const f = t.nazmos.hero.flow;
  const src = t.nazmos.hero.sources;

  const sources = [
    { label: src.csv, x: 12, y: 20 },
    { label: src.inventory, x: 30, y: 10 },
    { label: src.pos, x: 70, y: 12 },
    { label: src.supplier, x: 84, y: 30 },
    { label: src.financial, x: 88, y: 66 },
    { label: src.inventory, x: 16, y: 66 },
  ];

  return (
    <section className="relative overflow-hidden px-5 pb-16 pt-20 md:min-h-[100svh] md:px-8 md:pb-24 md:pt-28">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-50"
        style={{
          backgroundImage:
            "radial-gradient(color-mix(in oklch, var(--brand-teal) 7%, transparent) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse at 50% 45%, black 20%, transparent 70%)",
        }}
      />

      <div className="relative mx-auto max-w-5xl text-center">
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}
        >
          <motion.p
            variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_STANDARD } } }}
            className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-primary"
          >
            NazmOS
          </motion.p>

          <motion.h1
            variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_STANDARD } } }}
            className="mx-auto mt-5 max-w-3xl font-serif text-4xl font-normal leading-[1.05] tracking-[-0.02em] text-foreground md:text-7xl text-balance"
          >
            {t.nazmos.hero.title1}{" "}
            <span className="text-primary">{t.nazmos.hero.title2}</span>
          </motion.h1>

          <motion.p
            variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_STANDARD } } }}
            className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground md:text-lg"
          >
            {t.nazmos.hero.lead}
          </motion.p>
        </motion.div>
      </div>

      {/* The visualization */}
      <div className="relative mx-auto mt-16 max-w-4xl">
        <NazmosVisual sources={sources} flow={f} />
      </div>
    </section>
  );
}

function NazmosVisual({
  sources,
  flow,
}: {
  sources: { label: string; x: number; y: number }[];
  flow: { data: string; system: string; context: string; decision: string };
}) {
  // Layout over a 100x100 space
  const layout = {
    data: { x: 50, y: 6 },
    system: { x: 50, y: 42 },
    context: { x: 50, y: 68 },
    decision: { x: 50, y: 90 },
  };

  return (
    <div className="relative aspect-[4/3] w-full sm:aspect-[2/1]">
      {/* Sources (fragmented inputs) around the top/data band */}
      {sources.map((s, i) => (
        <motion.div
          key={i}
          className="absolute z-10 -translate-x-1/2 -translate-y-1/2"
          style={{ left: `${s.x}%`, top: `${s.y}%` }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 + i * 0.1 }}
        >
          <span className="rounded-md border border-border bg-card px-2.5 py-1 font-mono text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
            {s.label}
          </span>
        </motion.div>
      ))}

      {/* Data node */}
      <motion.div
        className="absolute left-1/2 z-10 -translate-x-1/2"
        style={{ top: `${layout.data.y}%` }}
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.6, ease: EASE_STANDARD }}
      >
        <span className="rounded-lg border border-border bg-card px-4 py-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-foreground">
          {flow.data}
        </span>
      </motion.div>

      {/* NAZMOS system core */}
      <motion.div
        className="absolute left-1/2 z-20 -translate-x-1/2 -translate-y-1/2"
        style={{ top: `${layout.system.y}%` }}
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 1.0, duration: 0.7, ease: EASE_STANDARD }}
      >
        <motion.div
          animate={{ boxShadow: ["0 0 30px color-mix(in oklch, var(--brand-teal) 30%, transparent)", "0 0 55px color-mix(in oklch, var(--brand-teal) 45%, transparent)", "0 0 30px color-mix(in oklch, var(--brand-teal) 30%, transparent)"] }}
          transition={{ duration: 5, repeat: Infinity, delay: 1.4 }}
          className="flex h-28 w-28 flex-col items-center justify-center rounded-full border border-primary/40 bg-card"
        >
          <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-primary">
            {flow.system}
          </span>
        </motion.div>
      </motion.div>

      {/* Context */}
      <motion.div
        className="absolute left-1/2 -translate-x-1/2"
        style={{ top: `${layout.context.y}%` }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.6, duration: 0.6 }}
      >
        <span className="rounded-lg border border-primary/35 bg-primary/5 px-4 py-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-foreground">
          {flow.context}
        </span>
      </motion.div>

      {/* Decision */}
      <motion.div
        className="absolute left-1/2 -translate-x-1/2"
        style={{ top: `${layout.decision.y}%` }}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 2.0, duration: 0.6, ease: EASE_STANDARD }}
      >
        <span className="rounded-lg border border-brand-gold/50 bg-brand-gold/[0.07] px-4 py-1.5 font-mono text-xs font-bold uppercase tracking-wider text-foreground">
          {flow.decision}
        </span>
      </motion.div>

      {/* Connecting lines */}
      <ConnectionLine from={{ x: 50, y: 9 }} to={{ x: 50, y: 34 }} delay={0.8} />
      <ConnectionLine from={{ x: 50, y: 50 }} to={{ x: 50, y: 64 }} delay={1.3} />
      <ConnectionLine from={{ x: 50, y: 72 }} to={{ x: 50, y: 86 }} delay={1.8} />
    </div>
  );
}

function ConnectionLine({
  from,
  to,
  delay,
}: {
  from: { x: number; y: number };
  to: { x: number; y: number };
  delay: number;
}) {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <motion.line
        x1={from.x} y1={from.y} x2={to.x} y2={to.y}
        stroke="var(--brand-teal)"
        strokeOpacity="0.4"
        strokeWidth="0.5"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ delay, duration: 0.8, ease: "easeInOut" }}
      />
    </svg>
  );
}
