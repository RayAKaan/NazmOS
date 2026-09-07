"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const EASE = [0.22, 1, 0.36, 1] as const;

interface CompanyOverlayProps {
  stacked?: boolean;
  goNazmos: () => void;
  goBack: () => void;
}

/**
 * CompanyOverlay — the in-universe "Nazmak" state (spec §07, §27).
 *
 * Level 2 of the communication hierarchy: who builds this, and what the
 * builder does. It replaces the thesis in the same environmental zone while
 * the network recedes behind it — the company is part of the space, not a
 * separate page.
 */
export function CompanyOverlay({ stacked, goNazmos, goBack }: CompanyOverlayProps) {
  const { t } = useI18n();
  const c = t.universe.company;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.5, ease: EASE }}
      className={cn(
        "pointer-events-none mx-auto w-full max-w-2xl px-5 text-center",
        stacked ? "mt-6" : "absolute inset-x-0 top-[16vh] z-20",
      )}
    >
      <p className="u-gold font-mono text-[11px] uppercase tracking-[0.28em]">{c.eyebrow}</p>
      <p className="u-gold-bright mt-4 font-serif text-4xl leading-tight md:text-6xl">
        {c.label}
      </p>
      <h2 className="u-ink mt-4 font-serif text-2xl leading-tight md:text-4xl">{c.title}</h2>
      <p className="u-ink-dim mx-auto mt-4 max-w-xl text-sm leading-relaxed md:text-base">
        {c.body}
      </p>

      <div className="pointer-events-auto mx-auto mt-8 flex max-w-sm flex-col items-center gap-2">
        <button
          type="button"
          onClick={goNazmos}
          className="u-gold-bg u-gold-ink focus-ring inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors hover:opacity-90 focus:outline-none"
        >
          {c.exploreProduct}
          <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={goBack}
          className="focus-ring u-ink-dim inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm transition-colors hover:bg-card focus:outline-none"
        >
          {t.universe.backToUniverse}
        </button>
        <div className="mt-2 flex items-center gap-4">
          <Link
            href="/privacy"
            className="focus-ring u-ink-faint text-xs transition-colors hover:u-ink-dim focus:outline-none"
          >
            {c.privacy}
          </Link>
          <Link
            href="/terms"
            className="focus-ring u-ink-faint text-xs transition-colors hover:u-ink-dim focus:outline-none"
          >
            {c.terms}
          </Link>
        </div>
      </div>
    </motion.div>
  );
}