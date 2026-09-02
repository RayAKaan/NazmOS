"use client";

import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Check, ArrowRight, ArrowLeft } from "lucide-react";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";

/**
 * DecisionCard — a branded sample decision moment.
 *
 * Shows the cinematic chain: issue detected → value at risk → recommendation
 * → review → approve → action. Numbers are clearly labelled SAMPLE.
 */
export function DecisionCard() {
  const { t, dir } = useI18n();
  const c = t.nazmos.decision;

  return (
    <div className="mx-auto w-full max-w-xl overflow-hidden rounded-xl border border-border bg-card">
      {/* Sample header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
          {c.badge}
        </span>
        <span className="rounded-full border border-brand-gold/40 bg-brand-gold/[0.08] px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-foreground">
          {c.sample}
        </span>
      </div>

      {/* Issue */}
      <div className="px-5 py-4">
        <Step icon={<AlertIcon />} label={c.deadInventory} value="34 units · no recent sales" tone="muted" />
      </div>

      {/* Value at risk */}
      <div className="border-t border-border px-5 py-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">{c.valueAtRisk}</span>
          <span className="font-serif text-2xl font-medium tabular-nums text-brand-gold">
            SAR 12,400
          </span>
        </div>
      </div>

      {/* Chain */}
      <div className="border-t border-border px-5 py-4">
        <ChainRow steps={[c.recommendation, c.review, c.approve, c.action]} dir={dir} />
      </div>

      <div className="border-t border-border bg-muted/30 px-5 py-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {c.estimateLabel}
        </p>
      </div>
    </div>
  );
}

function ChainRow({ steps, dir }: { steps: string[]; dir: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center gap-2">
          <motion.span
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.12, ease: EASE_STANDARD }}
            className="rounded-md border border-border bg-card px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-foreground"
          >
            {s}
          </motion.span>
          {i < steps.length - 1 && (
            <Arrow dir={dir} />
          )}
        </div>
      ))}
    </div>
  );
}

function Arrow({ dir }: { dir: string }) {
  const Icon = dir === "rtl" ? ArrowLeft : ArrowRight;
  return <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />;
}

function AlertIcon() {
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-destructive/10">
      <Check className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
    </span>
  );
}

function Step({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: string }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        {icon}
        <div>
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className={cn("text-xs", tone === "muted" ? "text-muted-foreground" : "text-foreground")}>{value}</p>
        </div>
      </div>
    </div>
  );
}
