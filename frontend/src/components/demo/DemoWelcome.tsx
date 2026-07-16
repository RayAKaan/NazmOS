"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { ArrowRight, Sparkles, Shield, Zap, Globe } from "lucide-react";

export function DemoWelcome() {
  const { nextStep } = useDemoEngine();
  const { t, locale } = useI18n();

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col items-center justify-center p-6 md:p-12 relative overflow-hidden">
      {/* Ambient light effects */}
      <div className="absolute inset-0 bg-gradient-to-b from-accent-blue/5 via-transparent to-transparent" />
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-accent-blue/5 rounded-full blur-[120px]" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent-purple/5 rounded-full blur-[120px]" />

      {/* Floating particles */}
      {Array.from({ length: 20 }, (_, i) => (
        <motion.div
          key={i}
          className="absolute w-1 h-1 rounded-full bg-accent-blue/20"
          initial={{
            x: Math.random() * (typeof window !== "undefined" ? window.innerWidth : 1200),
            y: Math.random() * (typeof window !== "undefined" ? window.innerHeight : 800),
            opacity: 0,
          }}
          animate={{
            y: [null, Math.random() * -200],
            opacity: [0, 0.6, 0],
          }}
          transition={{
            duration: 3 + Math.random() * 4,
            repeat: Infinity,
            delay: Math.random() * 3,
          }}
        />
      ))}

      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="relative z-10 text-center max-w-3xl"
      >
        {/* Animated logo */}
        <motion.div
          initial={{ opacity: 0, y: 30, rotateY: -90 }}
          animate={{ opacity: 1, y: 0, rotateY: 0 }}
          transition={{ delay: 0.2, duration: 0.6, type: "spring" }}
          className="w-24 h-24 rounded-2xl bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center mx-auto mb-8 shadow-lg shadow-accent-blue/20"
        >
          <motion.span
            animate={{ scale: [1, 1.05, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="text-white font-bold text-5xl font-serif"
          >
            ن
          </motion.span>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-accent-blue/10 border border-accent-blue/20 rounded-full mb-6"
        >
          <Sparkles className="w-4 h-4 text-accent-blue" />
          <span className="text-sm text-accent-blue font-medium">{t.demo.welcome.badge}</span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="text-4xl md:text-6xl lg:text-7xl font-serif font-bold mb-4 leading-tight"
        >
          {t.demo.welcome.title1}
          <br />
          <span className="bg-gradient-to-r from-accent-blue to-accent-purple bg-clip-text text-transparent">
            {t.demo.welcome.title2}
          </span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="text-lg md:text-xl text-text-secondary mb-4 max-w-xl mx-auto"
        >
          {locale === "ar" ? t.demo.welcome.subtitleAr : t.demo.welcome.subtitle}
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.55 }}
          className="text-base text-text-muted mb-10 max-w-lg mx-auto"
          dir="rtl"
        >
          {t.demo.welcome.subtitleAr}
        </motion.p>

        <motion.button
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7 }}
          onClick={nextStep}
          className="group px-8 py-4 bg-gradient-to-r from-accent-blue to-accent-purple text-white font-medium text-lg rounded-xl hover:shadow-lg hover:shadow-accent-blue/30 transition-all flex items-center gap-3 mx-auto hover:-translate-y-0.5"
        >
          {t.beginExperience}
          <motion.div
            animate={{ x: [0, 5, 0] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          >
            <ArrowRight className="w-5 h-5" />
          </motion.div>
        </motion.button>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1 }}
          className="mt-12 flex flex-wrap items-center justify-center gap-6 text-sm text-text-muted"
        >
          {[
            { icon: Shield, label: t.demo.welcome.stats.saved, color: "text-accent-green" },
            { icon: Zap, label: t.demo.welcome.stats.stores, color: "text-accent-yellow" },
            { icon: Globe, label: t.demo.welcome.stats.madeIn, color: "text-accent-purple" },
          ].map((stat, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1.2 + i * 0.1 }}
              className="flex items-center gap-2"
            >
              <stat.icon className={`w-4 h-4 ${stat.color}`} />
              <span>{stat.label}</span>
            </motion.div>
          ))}
        </motion.div>
      </motion.div>
    </div>
  );
}
