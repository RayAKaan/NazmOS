"use client";

import { motion } from "framer-motion";
import { ArrowRight, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { SplitText } from "@/components/ui/SplitText";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

const SIGNALS = [
  { key: "sales", x: -3, y: 1 },
  { key: "inventory", x: 3, y: 1.5 },
  { key: "suppliers", x: -2, y: 2.5 },
  { key: "cost", x: 2, y: 3 },
  { key: "demand", x: 0, y: 3.5 },
] as const;

/**
 * NazmakHero — the company-level hero.
 *
 * Left: editorial company thesis. Right: a living system where isolated
 * business signals converge, connect, and NAZMOS appears as the system
 * linking them. Cinematic Framer Motion sequence, then settles to ambient.
 */
export function NazmakHero() {
  const { t, dir } = useI18n();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  return (
    <section className="relative overflow-hidden px-5 pb-16 pt-20 md:min-h-[92svh] md:px-8 md:pb-24 md:pt-28">
      {/* Subtle convergence grid */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.5]"
        style={{
          backgroundImage:
            "radial-gradient(color-mix(in oklch, var(--brand-teal) 8%, transparent) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse at 70% 40%, black 30%, transparent 70%)",
        }}
      />

      <div className="relative mx-auto grid max-w-7xl items-center gap-14 lg:grid-cols-[1.05fr_.95fr]">
        {/* Copy */}
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}
          className="min-w-0"
        >
          <motion.p
            variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_STANDARD } } }}
            className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-primary"
          >
            Nazmak
          </motion.p>

          <motion.h1
            variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_STANDARD } } }}
            className="mt-5 max-w-2xl font-serif text-4xl font-normal leading-[1.02] tracking-[-0.02em] text-foreground md:text-6xl text-balance"
          >
            <SplitText text={t.company.hero.title1} />
            <br />
            <SplitText text={t.company.hero.title2} />
          </motion.h1>

          <motion.p
            variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_STANDARD } } }}
            className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg"
          >
            {t.company.hero.lead}
          </motion.p>

          <motion.div
            variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE_STANDARD } } }}
            className="mt-8 flex flex-col gap-3 sm:flex-row"
          >
            <Link
              href="/products/nazmos"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
            >
              {t.company.hero.cta} <Arrow className="h-4 w-4" aria-hidden="true" />
            </Link>
            <a
              href="#free-audit"
              className="inline-flex items-center justify-center rounded-lg border border-border bg-card px-6 py-3.5 font-semibold text-foreground transition-colors hover:bg-muted"
            >
              {t.company.hero.ctaSecondary}
            </a>
          </motion.div>
        </motion.div>

        {/* System visualization */}
        <NazmakHeroSystem />
      </div>
    </section>
  );
}

/**
 * NazmakHeroSystem — the isolated signals converging into NAZMOS.
 * Sequence:
 *   0s   isolated signals fade in
 *   1s   connecting lines draw between them
 *   2s   NAZMOS node appears at the center, glowing
 *   3s   a business insight emerges below
 *   then ambient slow pulse only.
 */
function NazmakHeroSystem() {
  const { t } = useI18n();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.8, delay: 0.3 }}
      className="relative mx-auto aspect-square w-full max-w-[440px]"
      role="img"
      aria-label={t.company.hero.systemLabel}
    >
      {/* Center: NAZMOS */}
      <motion.div
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.7, delay: 1.6, ease: EASE_STANDARD }}
        className="absolute left-1/2 top-1/2 z-20 -translate-x-1/2 -translate-y-1/2"
      >
        <motion.div
          animate={{
            boxShadow: [
              "0 0 0px color-mix(in oklch, var(--brand-teal) 0%, transparent)",
              "0 0 40px color-mix(in oklch, var(--brand-teal) 35%, transparent)",
              "0 0 0px color-mix(in oklch, var(--brand-teal) 0%, transparent)",
            ],
          }}
          transition={{ duration: 4, repeat: Infinity, delay: 2.2 }}
          className="flex h-28 w-28 flex-col items-center justify-center rounded-full border border-primary/40 bg-card"
        >
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-primary">
            {t.company.hero.denominator}
          </span>
        </motion.div>
      </motion.div>

      {/* Signals converge toward the center */}
      {SIGNALS.map((s) => {
        const cx = 50 + s.x * 14;
        const cy = 50 + s.y * 14;
        return (
          <SignalNode
            key={s.key}
            label={t.company.hero.signals[s.key]}
            cx={cx}
            cy={cy}
            delay={0.4 + (s.x + s.y) * 0.05}
            lineDelay={1.1}
          />
        );
      })}

      {/* Insight emerges below center */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 2.4, ease: EASE_STANDARD }}
        className="absolute bottom-2 left-1/2 -translate-x-1/2"
      >
        <div className="rounded-lg border border-border bg-card px-4 py-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            {t.company.hero.insight}
          </span>
          <span className="ml-2 inline-block h-1.5 w-1.5 rounded-full bg-brand-gold" aria-hidden="true" />
        </div>
      </motion.div>
    </motion.div>
  );
}

function SignalNode({
  label,
  cx,
  cy,
  delay,
  lineDelay,
}: {
  label: string;
  cx: number;
  cy: number;
  delay: number;
  lineDelay: number;
}) {
  return (
    <motion.div
      className="absolute z-10 -translate-x-1/2 -translate-y-1/2"
      style={{ left: `${cx}%`, top: `${cy}%` }}
      initial={{ opacity: 0, scale: 0.6 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, delay, ease: EASE_STANDARD }}
    >
      <div className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 shadow-subtle">
        <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-foreground">
          {label}
        </span>
      </div>
    </motion.div>
  );
}
