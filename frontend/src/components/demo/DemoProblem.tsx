"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { AlertTriangle, Clock, Calculator, TrendingDown, ArrowRight } from "lucide-react";

export function DemoProblem() {
  const { nextStep } = useDemoEngine();
  const { t, locale } = useI18n();

  const icons = [AlertTriangle, TrendingDown, Clock, Calculator];
  const colors = ["text-red-400", "text-yellow-400", "text-purple-400", "text-red-400"];
  const bgs = ["bg-red-500/10", "bg-yellow-500/10", "bg-purple-500/10", "bg-red-500/10"];
  const borders = ["border-red-500/20", "border-yellow-500/20", "border-purple-500/20", "border-red-500/20"];

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col items-center justify-center p-6 md:p-12">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-12 max-w-2xl"
      >
        <div className="text-sm text-red-400 font-medium uppercase tracking-wider mb-3">{t.demo.problem.beforeNazm}</div>
        <h2 className="text-3xl md:text-4xl font-serif font-bold mb-3">
          {locale === "ar" ? t.demo.problem.titleAr : t.demo.problem.title}{" "}
          <span className="text-red-400">{locale === "ar" ? t.demo.problem.titleHardAr : t.demo.problem.titleHard}</span>
        </h2>
        <p className="text-text-secondary text-lg" dir="rtl">
          {t.demo.problem.titleAr} <span className="text-red-400">{t.demo.problem.titleHardAr}</span>
        </p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl w-full mb-10">
        {t.demo.problem.points.map((point: any, i: number) => {
          const Icon = icons[i];
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 30, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: 0.2 + i * 0.15, type: "spring", stiffness: 100 }}
              whileHover={{ scale: 1.02, y: -2 }}
              className={`p-5 rounded-xl border ${borders[i]} ${bgs[i]} cursor-default`}
            >
              <div className="flex items-start gap-4">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.4 + i * 0.15, type: "spring" }}
                  className={`p-2 rounded-lg ${bgs[i]}`}
                >
                  <Icon className={`w-5 h-5 ${colors[i]}`} />
                </motion.div>
                <div>
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 + i * 0.1 }}
                    className={`text-2xl font-bold font-mono ${colors[i]}`}
                  >
                    {point.stat}
                  </motion.div>
                  <div className="font-medium text-sm mt-1">{point.label}</div>
                  <div className="text-xs text-text-muted mt-0.5" dir="rtl">{point.labelAr}</div>
                  <p className="text-xs text-text-muted mt-2">{point.desc}</p>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1 }}
        className="text-center"
      >
        <p className="text-lg text-text-secondary mb-2">
          {locale === "ar" ? t.demo.problem.transitionAr : t.demo.problem.transition}{" "}
          <span className="text-accent-blue font-semibold">{locale === "ar" ? t.demo.problem.transitionAccentAr : t.demo.problem.transitionAccent}</span>?
        </p>
        <p className="text-sm text-text-muted mb-6" dir="rtl">
          {t.demo.problem.transitionAr} <span className="text-accent-blue">{t.demo.problem.transitionAccentAr}</span>؟
        </p>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.98 }}
          onClick={nextStep}
          className="px-6 py-3 bg-gradient-to-r from-accent-blue to-accent-purple text-white font-medium rounded-xl transition-all flex items-center gap-2 mx-auto shadow-lg shadow-accent-blue/20"
        >
          {t.seeHowItWorks}
          <ArrowRight className="w-4 h-4" />
        </motion.button>
      </motion.div>
    </div>
  );
}
