"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, ArrowUpRight, Sparkles } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { DomainId } from "./data";

const EASE = [0.22, 1, 0.36, 1] as const;

interface StackedProps {
  stacked?: boolean;
}

function PanelShell({
  stacked,
  children,
  className,
  onBack,
  backLabel,
}: StackedProps & {
  children: React.ReactNode;
  className?: string;
  onBack?: () => void;
  backLabel?: string;
}) {
  const { dir } = useI18n();
  return (
    <motion.div
      initial={{ opacity: 0, x: dir === "rtl" ? -24 : 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: dir === "rtl" ? -16 : 16 }}
      transition={{ duration: 0.45, ease: EASE }}
      className={cn(
        stacked
          ? "relative z-40 mt-5 u-panel backdrop-blur-xl"
          : "absolute inset-y-0 end-0 z-40 flex flex-col border-s u-panel-side backdrop-blur-xl md:max-w-[400px]",
        "w-full overflow-y-auto p-8",
        className,
      )}
    >
      {typeof onBack === "function" && (
        <button
          type="button"
          onClick={onBack}
          className="focus-ring mb-4 inline-flex items-center gap-1.5 self-start rounded-md px-1 py-0.5 font-mono text-[11px] uppercase tracking-[0.16em] text-foreground/45 transition-colors hover:text-foreground focus:outline-none"
        >
          <ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden="true" />
          {backLabel ?? ""}
        </button>
      )}
      {children}
    </motion.div>
  );
}

export function DomainFocus({
  domain,
  stacked,
  goNazmos,
  goBack,
}: {
  domain: DomainId;
} & StackedProps & {
  goNazmos: () => void;
  goBack: () => void;
}) {
  const { t } = useI18n();
  const copy = t.universe.nodes[domain];
  // cost is the value/capital face of the system — gold emphasises it in both
  // worlds (spec §33: financial value gets real gold, not pseudo-glow).
  const isValue = domain === "cost";

  return (
    <PanelShell stacked={stacked} onBack={goBack} backLabel={t.universe.focus.back}>
      <p className={cn("font-mono text-[11px] uppercase tracking-[0.24em]", isValue ? "u-gold" : "u-teal")}>
        {copy.label}
      </p>
      <h2 className="u-ink mt-3 font-serif text-3xl leading-tight md:text-[2.4rem]">{copy.title}</h2>
      <p className="u-ink-dim mt-4 text-sm leading-relaxed">{copy.body}</p>

      {/* Demand is directional: history → signal → forecast (the future leaves
          signals). The three-step progression makes the direction visible. */}
      {domain === "demand" && (
        <div className="mt-6">
          <p className="u-ink-faint font-mono text-[10px] uppercase tracking-[0.2em]">
            {t.universe.forecast.label}
          </p>
          <div className="mt-2.5 flex items-center gap-1.5">
            {t.universe.forecast.steps.map((s: string, i: number) => (
              <span key={s} className="flex items-center gap-1.5">
                <span className="u-ink-dim rounded-full border border-border px-2.5 py-1 text-[11px]">
                  {s}
                </span>
                {i < t.universe.forecast.steps.length - 1 && (
                  <ArrowRight className="u-teal h-3.5 w-3.5 rtl:rotate-180" aria-hidden="true" />
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6">
        <p className="u-ink-faint font-mono text-[10px] uppercase tracking-[0.2em]">
          {copy.relatesLabel}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {copy.relates.map((r: string) => (
            <span
              key={r}
              className={cn(
                "u-ink-dim rounded-full border px-2.5 py-1 text-[11px]",
                isValue ? "u-gold-border" : "u-teal-border",
              )}
            >
              {r}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-8 flex flex-col gap-2">
        <button
          type="button"
          onClick={goNazmos}
          className={cn(
            "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors hover:opacity-90 focus-ring focus:outline-none",
            isValue ? "u-gold-bg u-gold-ink" : "u-teal-bg u-teal-ink",
          )}
        >
          {t.universe.focus.cta}
          <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={goBack}
          className="u-ink-dim rounded-lg border border-border px-4 py-2.5 text-sm transition-colors hover:bg-card focus-ring focus:outline-none"
        >
          {t.universe.backToUniverse}
        </button>
      </div>
    </PanelShell>
  );
}

export function NazmosConvergence({
  stacked,
  goAudit,
  goBack,
}: StackedProps & { goAudit: () => void; goBack: () => void }) {
  const { t } = useI18n();

  return (
    <PanelShell stacked={stacked} onBack={goBack} backLabel={t.universe.backToUniverse}>
      <div className="flex items-center gap-2">
        <Sparkles className="u-gold h-4 w-4" aria-hidden="true" />
        <p className="u-gold font-mono text-[11px] uppercase tracking-[0.24em]">
          {t.universe.nodes.nazmos.label}
        </p>
      </div>
      <h2 className="u-ink mt-3 font-serif text-3xl leading-tight md:text-[2.4rem]">
        {t.universe.convergence.title}
      </h2>
      <p className="u-ink-dim mt-4 text-sm leading-relaxed">{t.universe.convergence.body}</p>
      <p className="u-ink-dim mt-4 rounded-lg border border-border bg-card/60 p-3 font-mono text-[11px] leading-relaxed">
        {t.universe.convergence.productHint}
      </p>

      <div className="mt-8 flex flex-col gap-2">
        {/* The Business Audit opens NazmOS's financial view — value emphasised
            in real gold in both modes (spec §36). */}
        <button
          type="button"
          onClick={goAudit}
          className="u-gold-bg u-gold-ink inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors hover:opacity-90 focus-ring focus:outline-none"
        >
          {t.universe.requestAudit}
          <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
        </button>
        <Link
          href="/products/nazmos"
          className="u-ink-dim inline-flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm transition-colors hover:bg-card focus-ring focus:outline-none"
        >
          {t.universe.productPage}
          <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
        </Link>
        <button
          type="button"
          onClick={goBack}
          className="rounded-lg px-4 py-2 text-left text-xs text-foreground/45 transition-colors hover:text-foreground"
        >
          {t.universe.backToUniverse}
        </button>
      </div>
    </PanelShell>
  );
}