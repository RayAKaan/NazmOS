"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowDown, Boxes, Database, FolderTree, ShieldCheck, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { useAudit } from "@/components/landing/audit-context";
import { useSafeReducedMotion } from "./useSafeReducedMotion";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import { SAMPLE_FINDINGS, SAMPLE_GRAPH } from "./types";
import { GraphDiagram } from "./GraphDiagram";

/**
 * HeroOS — the hero's live miniature of NazmOS operating (§4-6). A vertical pipeline
 * shows business data converging into NazmOS (memory → knowledge graph → analysis →
 * decision → recommendation). The finding below is interactive: selecting it expands
 * evidence. All figures are deterministic demo values or the visitor's own live audit
 * result — never fabricated telemetry. Reduced-motion renders a static, meaningful OS.
 */
export function HeroOS({ className }: { className?: string }) {
  const { t } = useI18n();
  const { result } = useAudit();
  const reduced = useSafeReducedMotion();
  const [open, setOpen] = useState<string | null>(SAMPLE_FINDINGS[0].id);

  const finding = SAMPLE_FINDINGS[0];
  const live = result !== null;
  const moneyAtRisk = live
    ? result.summary.money_at_risk_sar
    : Number(finding.evidence.estimatedValue ?? 0);

  const Stage = ({
    icon,
    label,
    sub,
  }: {
    icon: React.ReactNode;
    label: string;
    sub?: string;
  }) => (
    <motion.div
      initial={reduced ? undefined : { opacity: 0, x: 10 }}
      animate={reduced ? undefined : { opacity: 1, x: 0 }}
      transition={{ duration: 0.4 }}
      className="flex items-center gap-3 rounded-xl border border-border bg-card px-3 py-2"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-foreground">{label}</p>
        {sub && <p className="truncate text-[11px] text-muted-foreground">{sub}</p>}
      </div>
    </motion.div>
  );

  const Divider = () => (
    <div className="flex items-center justify-center py-1 text-muted-foreground/50" aria-hidden="true">
      <motion.span
        className="h-px w-px"
        animate={reduced ? undefined : { scaleY: [1, 8, 1], opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );

  return (
    <div className={cn("grid gap-4 lg:grid-cols-[1fr_1.1fr] lg:items-center", className)}>
      {/* Vertical operating pipeline */}
      <div className="min-w-0 rounded-3xl border border-border bg-card p-4 shadow-elevation-2">
        <div className="mb-3 flex items-center justify-between px-1">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
            {t.landing.hero.osLabel}
          </p>
          <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary">
            {live ? t.landing.hero.liveBadge : t.landing.hero.sampleLabel}
          </span>
        </div>

        <Stage icon={<Boxes className="h-4 w-4" aria-hidden="true" />} label={t.landing.hero.os.yourBusiness} sub="Sales · Inventory · Suppliers" />
        <Divider />
        <Stage icon={<Database className="h-4 w-4" aria-hidden="true" />} label={t.landing.hero.os.ingest} sub={t.landing.hero.os.ingestSub} />
        <Divider />
        <Stage icon={<FolderTree className="h-4 w-4" aria-hidden="true" />} label={t.landing.hero.os.memory} sub={t.landing.hero.os.memorySub} />
        <Divider />
        <Stage icon={<Zap className="h-4 w-4" aria-hidden="true" />} label={t.landing.hero.os.analyze} sub={t.landing.hero.os.analyzeSub} />
        <Divider />
        <Stage icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />} label={t.landing.hero.os.decide} sub={t.landing.hero.os.decideSub} />
      </div>

      {/* Interactive finding + mini graph */}
      <div className="min-w-0 space-y-4">
        <GraphDiagram nodes={SAMPLE_GRAPH.nodes.slice(0, 8)} edges={SAMPLE_GRAPH.edges.slice(0, 7)} interactive={false} className="h-44" />

        <button
          type="button"
          onClick={() => setOpen(open === finding.id ? null : finding.id)}
          aria-expanded={open === finding.id}
          className={cn(
            "w-full rounded-2xl border p-4 text-left transition-colors",
            finding.importance === "warning"
              ? "border-warning/30 bg-warning/[0.06]"
              : "border-destructive/30 bg-destructive/[0.06]"
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">{t.landing.labels.finding}</p>
            <ArrowDown className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden="true" />
          </div>
          <p className="mt-1 font-serif text-xl font-black text-foreground">{finding.title}</p>
          <div className="mt-2">
            <FigureHeadline value={moneyAtRisk} label={t.landing.hero.finding.estValue} size="secondary" tone="warning" currency="SAR" />
          </div>

          <div
            className={cn(
              "grid transition-all",
              open ? "mt-4 grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
            )}
          >
            <div className="overflow-hidden">
              <p className="text-sm leading-6 text-muted-foreground">{finding.summary}</p>
              <ul className="mt-3 space-y-1">
                {finding.evidence.details?.map((d) => (
                  <li key={d} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="h-1 w-1 rounded-full bg-primary" aria-hidden="true" />
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </button>

        {live && (
          <p className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
            <ShieldCheck className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
            {t.landing.hero.finding.liveNote}
          </p>
        )}
      </div>
    </div>
  );
}
