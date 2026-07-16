"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { Store, ChevronRight } from "lucide-react";

export function DemoHeader() {
  const { currentStep, totalSteps } = useDemoEngine();
  const { t } = useI18n();
  const stepLabels = t.demo.steps;

  return (
    <div className="bg-bg-card border-b border-border p-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center">
            <span className="text-white font-bold text-sm font-serif">ن</span>
          </div>
          <div>
            <h2 className="text-sm font-semibold">{t.demo.header.title}</h2>
            <p className="text-[10px] text-text-muted">Riyadh — Al Othaim Mall</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-xs text-text-muted">
            {stepLabels[currentStep] || `Step ${currentStep + 1}`}
          </div>
          <div className="flex gap-1">
            {Array.from({ length: totalSteps }, (_, i) => (
              <motion.div
                key={i}
                initial={false}
                animate={{
                  backgroundColor: i <= currentStep ? "rgb(59, 130, 246)" : "rgb(55, 65, 81)",
                  scale: i === currentStep ? 1.2 : 1,
                }}
                className="w-2 h-2 rounded-full"
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
