"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { ArrowRight, ArrowLeft, Sparkles, Zap, Shield, Globe } from "lucide-react";

export function DemoCTA() {
  const { t, locale } = useI18n();

  const features = [
    { icon: Zap, label: t.demo.cta.feature1, color: "text-accent-yellow" },
    { icon: Shield, label: t.demo.cta.feature2, color: "text-accent-green" },
    { icon: Globe, label: t.demo.cta.feature3, color: "text-accent-blue" },
    { icon: Sparkles, label: t.demo.cta.feature4, color: "text-accent-purple" },
  ];

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col items-center justify-center p-6 md:p-12 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-t from-accent-blue/5 via-transparent to-transparent" />
      <div className="absolute top-1/3 left-1/3 w-[500px] h-[500px] bg-accent-blue/5 rounded-full blur-[150px]" />
      <div className="absolute bottom-1/3 right-1/3 w-[500px] h-[500px] bg-accent-purple/5 rounded-full blur-[150px]" />

      {Array.from({ length: 30 }, (_, i) => (
        <motion.div
          key={i}
          className="absolute w-1 h-1 rounded-full bg-accent-blue/30"
          initial={{ x: Math.random() * (typeof window !== "undefined" ? window.innerWidth : 1200), y: Math.random() * (typeof window !== "undefined" ? window.innerHeight : 800), opacity: 0 }}
          animate={{ y: [null, Math.random() * -300], opacity: [0, 0.5, 0] }}
          transition={{ duration: 2 + Math.random() * 3, repeat: Infinity, delay: Math.random() * 3 }}
        />
      ))}

      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, type: "spring" }}
        className="relative z-10 text-center max-w-3xl"
      >
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="w-20 h-20 rounded-2xl bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center mx-auto mb-8 shadow-lg shadow-accent-blue/20"
        >
          <span className="text-white font-bold text-4xl font-serif">ن</span>
        </motion.div>

        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-3xl md:text-5xl font-serif font-bold mb-4"
        >
          {locale === "ar" ? t.demo.cta.titleAr : t.demo.cta.title}{" "}
          <span className="bg-gradient-to-r from-accent-blue to-accent-purple bg-clip-text text-transparent">
            {t.demo.cta.title2}
          </span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="text-xl text-text-secondary mb-4"
          dir="rtl"
        >
          {t.demo.cta.subtitleAr}
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45 }}
          className="text-base text-text-muted mb-8 max-w-lg mx-auto"
        >
          {t.demo.cta.subtitle}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10"
        >
          {features.map((f, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 + i * 0.1 }}
              className="flex flex-col items-center gap-2"
            >
              <f.icon className={`w-5 h-5 ${f.color}`} />
              <span className="text-sm text-text-secondary">{f.label}</span>
            </motion.div>
          ))}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.9 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <motion.a
            href="/register"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="px-8 py-4 bg-gradient-to-r from-accent-blue to-accent-purple text-white font-medium text-lg rounded-xl hover:shadow-lg hover:shadow-accent-blue/30 transition-all flex items-center gap-3"
          >
            {t.demo.cta.getStarted}
            <ArrowRight className="w-5 h-5" />
          </motion.a>

          <motion.a
            href="/login"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="px-8 py-4 bg-surface border border-border text-text-primary font-medium text-lg rounded-xl hover:bg-surface-hover transition-all flex items-center gap-3"
          >
            {t.demo.cta.learnMore}
            <ArrowLeft className="w-5 h-5" />
          </motion.a>
        </motion.div>
      </motion.div>
    </div>
  );
}
