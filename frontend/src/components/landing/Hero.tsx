"use client";

import { motion } from "framer-motion";
import { ArrowRight, ArrowLeft, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { SplitText } from "@/components/ui/SplitText";
import { HeroOS } from "@/components/landing/viz/HeroOS";
import { HeroPlate } from "@/components/landing/viz/HeroPlate";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
};
const stagger = { hidden: {}, visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } } };

/**
 * Hero — Pass 3 signature moment. Full-bleed brand-night plate (HeroPlate), copy
 * anchored low-left, HeroOS kept as the product window over the scrim. The single
 * page-wide arrow lives on the primary CTA; every other CTA is plain (§7).
 */
export function Hero() {
  const { t, dir } = useI18n();
  const Arrow = dir === "rtl" ? ArrowLeft : ArrowRight;

  return (
    <section className="relative overflow-hidden px-5 pb-16 pt-28 md:min-h-[88svh] md:px-8 md:pb-20 md:pt-36">
      <HeroPlate />

      <div className="relative mx-auto grid w-full max-w-7xl items-end gap-12 lg:grid-cols-[1.05fr_.95fr]">
        <motion.div variants={stagger} initial="hidden" animate="visible" className="min-w-0 space-y-7">
          <motion.div
            variants={fadeUp}
            className="inline-flex items-center gap-2 rounded-full border border-brand-cream/20 bg-brand-cream/[0.07] px-4 py-2 text-xs font-bold uppercase tracking-[0.2em] text-brand-cream backdrop-blur"
          >
            <ShieldCheck className="h-4 w-4 text-brand-gold" aria-hidden="true" />
            {t.landing.hero.badge}
          </motion.div>

          <motion.h1
            variants={fadeUp}
            className="max-w-4xl font-serif text-5xl font-black leading-[0.98] tracking-[-0.03em] text-brand-cream md:text-7xl"
          >
            <SplitText text={t.landing.hero.title1} />
            <br />
            <SplitText text={t.landing.hero.title2} />
          </motion.h1>

          <motion.p variants={fadeUp} className="max-w-2xl text-lg leading-8 text-brand-cream/75 md:text-xl">
            {t.landing.hero.subtitle}
          </motion.p>

          <motion.div variants={fadeUp} className="flex flex-col gap-3 sm:flex-row">
            <a
              href="#free-audit"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-amber px-6 py-4 font-bold text-brand-night transition-colors hover:bg-brand-amber/90"
            >
              {t.landing.hero.primaryCta} <Arrow className="h-4 w-4" aria-hidden="true" />
            </a>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center rounded-xl border border-brand-cream/25 px-6 py-4 font-semibold text-brand-cream transition-colors hover:border-brand-cream/45 hover:bg-brand-cream/[0.07]"
            >
              {t.landing.hero.secondaryCta}
            </a>
          </motion.div>

          <motion.p variants={fadeUp} className="text-sm text-brand-cream/60">
            {t.landing.hero.trust}
          </motion.p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="min-w-0"
        >
          <HeroOS className="ring-1 ring-brand-cream/15" />
        </motion.div>
      </div>
    </section>
  );
}