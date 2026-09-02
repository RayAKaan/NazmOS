"use client";

import { motion } from "framer-motion";
import { ArrowRight, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { NazmakSection } from "./section";
import { ScrollReveal } from "@/components/motion/ScrollReveal";
import { EASE_STANDARD } from "@/components/motion/ScrollReveal";
import { track } from "@/lib/analytics";

/**
 * NazmosIntro — the dominant NazmOS product section.
 * Feels like "here is the first system Nazmak built" — a product reveal,
 * with a clear path into the full product page.
 */
export function NazmosIntro() {
  const { t, dir } = useI18n();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  return (
    <NazmakSection id="nazmos" className="relative overflow-hidden">
      {/* Deep teal material band */}
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10"
        style={{
          background:
            "linear-gradient(160deg, color-mix(in oklch, var(--brand-teal-dark) 70%, transparent), color-mix(in oklch, var(--brand-teal-dark) 40%, transparent))",
          borderTop: "1px solid color-mix(in oklch, var(--brand-teal) 15%, transparent)",
          borderBottom: "1px solid color-mix(in oklch, var(--brand-teal) 15%, transparent)",
        }}
      />

      <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
        <ScrollReveal>
          <div>
            <span className="inline-flex items-center gap-3">
              <span className="h-px w-8 bg-primary/60" aria-hidden="true" />
              <span className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-muted-foreground">
                {t.company.nazmosIntro.badge}
              </span>
            </span>
            <h2 className="mt-6 font-serif text-4xl font-normal leading-tight tracking-tight text-foreground md:text-6xl">
              {t.company.nazmosIntro.title}
            </h2>
            <p className="mt-4 font-mono text-sm uppercase tracking-[0.2em] text-primary">
              {t.company.nazmosIntro.lead}
            </p>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg">
              {t.company.nazmosIntro.body}
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/products/nazmos"
                onClick={() => track("home.nazmos_opened", {})}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
              >
                {t.company.nazmosIntro.cta} <Arrow className="h-4 w-4" aria-hidden="true" />
              </Link>
              <a
                href="#how-works"
                className="inline-flex items-center justify-center rounded-lg border border-border bg-card px-6 py-3.5 font-semibold text-foreground transition-colors hover:bg-muted"
              >
                {t.company.nazmosIntro.ctaSecondary}
              </a>
            </div>
          </div>
        </ScrollReveal>

        {/* Visual: Nazmak ↓ NazmOS ↓ business understanding ↓ decisions */}
        <motion.div
          initial={{ opacity: 0, x: dir === "rtl" ? -24 : 24 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.8, ease: EASE_STANDARD }}
          className="relative"
        >
          <div className="rounded-xl border border-border bg-card/60 p-8">
            <SystemLadder />
          </div>
        </motion.div>
      </div>
    </NazmakSection>
  );
}

function SystemLadder() {
  const { t } = useI18n();
  const steps = [
    { label: "Nazmak", tone: "ivory" },
    { label: t.company.nazmosIntro.title, tone: "teal" },
    { label: "Business understanding", tone: "teal" },
    { label: "Decisions", tone: "gold" },
  ] as const;

  return (
    <div className="space-y-5">
      {steps.map((s, i) => (
        <motion.div
          key={s.label}
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: i * 0.15, ease: EASE_STANDARD }}
          className="flex items-center gap-4"
        >
          <div className="relative flex flex-1 items-center">
            <span
              className={
                s.tone === "gold"
                  ? "rounded-lg border border-brand-gold/50 bg-brand-gold/[0.08] px-5 py-3.5 font-serif text-lg text-foreground"
                  : s.tone === "teal"
                  ? "rounded-lg border border-primary/40 bg-primary/5 px-5 py-3.5 font-mono text-lg font-semibold tracking-tight text-foreground"
                  : "rounded-lg border border-border bg-card px-5 py-3.5 font-mono text-sm uppercase tracking-[0.2em] text-muted-foreground"
              }
              style={{ width: `${86 - i * 10}%` }}
            >
              {s.label}
            </span>
            {i < steps.length - 1 && (
              <ArrowDown className="mx-auto" aria-hidden="true" />
            )}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

function ArrowDown({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={"h-4 w-4 shrink-0 text-muted-foreground " + (className ?? "")} fill="none" aria-hidden="true">
      <path d="M12 5v14m0 0l-5-5m5 5l5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
