"use client";

import { motion } from "framer-motion";
import { ArrowRight, ArrowLeft, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useAudit } from "@/components/landing/audit-context";
import { SplitText } from "@/components/ui/SplitText";
import { AmbientBackground } from "@/components/ui/AmbientBackground";
import { ShineBorder } from "@/components/ui/ShineBorder";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/utils";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
};
const stagger = { hidden: {}, visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } } };

const SAMPLE_ROWS = [
  { label: "Dead stock", value: 41000, tone: "text-destructive" },
  { label: "Overstock", value: 27000, tone: "text-warning" },
  { label: "Stockout risk", value: 143000, tone: "text-destructive" },
  { label: "Margin leakage", value: 12000, tone: "text-success" },
] as const;

function Money({ value }: { value: number }) {
  return <span className="tabular-nums">{formatCurrency(value).replace(/SAR\s?/, "SAR ")}</span>;
}

function AuditVisual() {
  const { t, dir } = useI18n();
  const { result } = useAudit();
  const live = result !== null;
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  const rows = live
    ? [
        { label: "Dead stock", value: result.summary.dead_stock_value_sar, tone: "text-destructive" },
        { label: "Overstock", value: result.summary.overstock_value_sar, tone: "text-warning" },
        { label: "Stockout risk", value: result.summary.stockout_risk_value_sar, tone: "text-destructive" },
        { label: "Margin leakage", value: result.summary.margin_leakage_sar, tone: "text-success" },
      ]
    : [...SAMPLE_ROWS];

  const headline = live
    ? formatCurrency(result.summary.money_at_risk_sar || 0)
    : formatCurrency(SAMPLE_ROWS.reduce((s, r) => s + r.value, 0));

  return (
    <div className="relative">
      <div className="rounded-3xl border border-border bg-card shadow-elevation-2">
        <div className="border-b border-border p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                {live ? t.landing.hero.liveBadge : "Money Audit"}
              </p>
              <p className="mt-1 font-serif text-3xl font-black tracking-[-0.02em] text-foreground tabular-nums">
                {headline}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {live
                  ? "could be tied up in your store"
                  : t.landing.hero.sampleTitle}
              </p>
            </div>
            <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
              {t.landing.hero.sampleLabel}
            </span>
          </div>
        </div>
        <div className="grid gap-3 p-6">
          {rows.map((r) => (
            <div
              key={r.label}
              className="flex items-center justify-between gap-3 rounded-2xl border border-border bg-muted/30 px-4 py-3"
            >
              <span className="text-sm text-muted-foreground">{r.label}</span>
              <span className={cn("font-serif text-xl font-black tabular-nums", r.tone)}>
                <Money value={r.value} />
              </span>
            </div>
          ))}
        </div>
        {!live && (
          <div className="border-t border-border p-6">
            <p className="text-xs leading-5 text-muted-foreground">{t.landing.hero.sampleNote}</p>
            <a
              href="#free-audit"
              className="mt-3 inline-flex items-center gap-1.5 text-sm font-bold text-primary hover:underline"
            >
              {t.landing.hero.idle.cta} <Arrow className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
        )}
        {live && (
          <div className="flex items-center gap-3 border-t border-border p-6">
            <ShieldCheck className="h-5 w-5 shrink-0 text-success" aria-hidden="true" />
            <p className="text-xs leading-5 text-muted-foreground">
              {Intl.NumberFormat("en-SA").format(result.summary.row_count)} rows · confidence{" "}
              {Math.round(result.summary.confidence_score)}%
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export function Hero() {
  const { t, dir } = useI18n();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  return (
    <section className="relative overflow-hidden px-5 py-20 md:px-8 md:py-28">
      <AmbientBackground />
      <div className="absolute inset-0 opacity-[0.025] [background-image:linear-gradient(var(--foreground)_1px,transparent_1px),linear-gradient(90deg,var(--foreground)_1px,transparent_1px)] [background-size:72px_72px]" />

      <div className="relative mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[1.05fr_.95fr]">
        <motion.div variants={stagger} initial="hidden" animate="visible" className="space-y-7">
          <motion.div
            variants={fadeUp}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-4 py-2 text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground"
          >
            <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
            {t.landing.hero.badge}
          </motion.div>

          <motion.h1
            variants={fadeUp}
            className="max-w-4xl font-serif text-5xl font-black leading-[0.98] tracking-[-0.03em] text-foreground md:text-7xl"
          >
            <SplitText text={t.landing.hero.title1} />
            <br />
            <SplitText text={t.landing.hero.title2} delay={0.15 * (dir === "ltr" ? 1 : 1)} />
          </motion.h1>

          <motion.p variants={fadeUp} className="max-w-2xl text-lg leading-8 text-muted-foreground md:text-xl">
            {t.landing.hero.subtitle}
          </motion.p>

          <motion.div variants={fadeUp} className="flex flex-col gap-3 sm:flex-row">
            <ShineBorder className="inline-flex rounded-xl">
              <a
                href="#free-audit"
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-6 py-4 font-bold text-primary-foreground hover:bg-primary/90"
              >
                {t.landing.hero.primaryCta} <Arrow className="h-4 w-4" aria-hidden="true" />
              </a>
            </ShineBorder>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center rounded-xl border border-border px-6 py-4 font-semibold text-foreground hover:bg-muted"
            >
              {t.landing.hero.secondaryCta}
            </a>
          </motion.div>

          <motion.p variants={fadeUp} className="text-sm text-muted-foreground">
            {t.landing.hero.trust}
          </motion.p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7 }}
        >
          <AuditVisual />
        </motion.div>
      </div>
    </section>
  );
}
