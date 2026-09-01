"use client";

import { motion } from "framer-motion";
import { ArrowRight, ArrowLeft, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { SplitText } from "@/components/ui/SplitText";
import { AmbientBackground } from "@/components/ui/AmbientBackground";
import { ShineBorder } from "@/components/ui/ShineBorder";
import { HeroOS } from "@/components/landing/viz/HeroOS";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
};
const stagger = { hidden: {}, visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } } };

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
          <HeroOS />
        </motion.div>
      </div>
    </section>
  );
}
