'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { ButtonWithIcon } from '@/components/ui/ButtonWithIcon';
import { useI18n } from '@/lib/i18n';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      ease: [0.25, 0.1, 0.25, 1],
    },
  },
};

export function Hero() {
  const { t } = useI18n();

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-bg-primary via-bg-primary to-bg-secondary" />
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-accent/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-accent/3 rounded-full blur-[100px]" />
        <div className="absolute inset-0 grain" />
      </div>

      <div className="container mx-auto px-6 py-32 relative z-10">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="max-w-4xl mx-auto text-center"
        >
          <motion.div variants={itemVariants} className="mb-8">
            <span className="inline-flex items-center gap-2 px-4 py-2 border border-border-primary bg-bg-secondary">
              <span className="w-1.5 h-1.5 bg-accent-primary" />
              <span className="font-sans text-xs uppercase tracking-widest text-text-secondary">
                {t.hero.badge}
              </span>
            </span>
          </motion.div>

          <motion.div variants={itemVariants}>
            <h1 className="font-serif text-5xl md:text-6xl lg:text-7xl xl:text-8xl font-normal tracking-tight text-text-primary mb-6 leading-[1.1]">
              {t.hero.title1}
              <br />
              <span className="text-accent-primary">{t.hero.title2}</span>
            </h1>
          </motion.div>

          <motion.div variants={itemVariants}>
            <p className="font-sans text-lg md:text-xl text-text-secondary max-w-2xl mx-auto mb-10 leading-relaxed">
              {t.hero.subtitle}
            </p>
          </motion.div>

          <motion.div variants={itemVariants} className="mb-12">
            <div className="flex items-center justify-center gap-4 mb-8">
              <div className="flex -space-x-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div
                    key={i}
                    className="w-10 h-10 bg-bg-tertiary border-2 border-bg-primary flex items-center justify-center"
                  >
                    <span className="font-mono text-xs text-text-muted">{i}</span>
                  </div>
                ))}
              </div>
              <span className="font-sans text-sm text-text-muted">
                {t.hero.trusted}
              </span>
            </div>
          </motion.div>

          <motion.div variants={itemVariants} className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/register">
              <ButtonWithIcon className="w-full sm:w-auto">
                {t.hero.startFree}
              </ButtonWithIcon>
            </Link>
            <Link 
              href="/demo"
              className="h-11 px-6 inline-flex items-center justify-center gap-2 font-sans text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
            >
              {t.hero.viewDemo}
              <ArrowRight className="w-4 h-4" />
            </Link>
          </motion.div>
        </motion.div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-bg-primary to-transparent" />
      
      <motion.div
        className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2 }}
      >
        <span className="font-sans text-xs uppercase tracking-widest text-text-muted">{t.hero.scroll}</span>
        <div className="w-px h-12 bg-gradient-to-b from-accent-primary to-transparent" />
      </motion.div>
    </section>
  );
}
