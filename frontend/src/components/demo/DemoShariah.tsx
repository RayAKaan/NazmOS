"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { formatCurrency } from "@/lib/utils";
import { ShieldCheck, ArrowRight, ArrowLeft, AlertCircle, CheckCircle2, HeartHandshake, Scale, Coins } from "lucide-react";

export function DemoShariah() {
  const { nextStep, prevStep } = useDemoEngine();
  const [activeTab, setActiveTab] = useState<"ihtikar" | "zakat" | "halal">("ihtikar");
  const [zakatBase, setZakatBase] = useState(140000);

  return (
    <div className="min-h-screen pt-24 pb-16 px-4 md:px-8 max-w-6xl mx-auto flex flex-col justify-between">
      <div className="space-y-8">
        {/* Header Badge */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6"
        >
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 border border-green-500/30 text-green-400 text-xs font-semibold uppercase tracking-wider mb-3 shadow-[0_0_15px_rgba(34,197,94,0.3)]">
              <ShieldCheck className="w-3.5 h-3.5 animate-pulse" /> Fiqh al-Mu'amalat Guardrails
            </div>
            <h1 className="text-3xl md:text-4xl font-black tracking-tight bg-gradient-to-r from-white via-white/90 to-white/60 bg-clip-text text-transparent">
              Shariah Commercial & Ethical Guardrails
            </h1>
            <p className="text-text-secondary text-sm md:text-base mt-2 max-w-3xl">
              In an Islamic economy, commerce is governed by Amanah (Trustworthiness) and Barakah (Blessing). Explore our built-in Halal screening, Anti-Ihtikar ethical guards, and retail ethics guardrails.
            </p>
          </div>

          <div className="flex gap-2 bg-surface p-1.5 rounded-2xl border border-white/10 shrink-0">
            <button
              onClick={() => setActiveTab("ihtikar")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${activeTab === "ihtikar" ? "bg-green-600 text-white shadow-lg" : "text-text-secondary hover:text-white"}`}
            >
              Anti-Ihtikar Ethics
            </button>
            <button
              onClick={() => setActiveTab("zakat")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${activeTab === "zakat" ? "bg-green-600 text-white shadow-lg" : "text-text-secondary hover:text-white"}`}
            >
              Ethics Guardrails
            </button>
            <button
              onClick={() => setActiveTab("halal")}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${activeTab === "halal" ? "bg-green-600 text-white shadow-lg" : "text-text-secondary hover:text-white"}`}
            >
              Halal SKU Screening
            </button>
          </div>
        </motion.div>

        {/* Tab Content Box */}
        <div className="bg-surface/80 backdrop-blur-xl border border-white/10 rounded-3xl p-6 md:p-8 shadow-2xl">
          <AnimatePresence mode="wait">
            {activeTab === "ihtikar" && (
              <motion.div
                key="ihtikar"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.3 }}
                className="space-y-6"
              >
                <div className="flex items-center gap-3">
                  <div className="p-3 rounded-2xl bg-green-500/20 text-green-400">
                    <Scale className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white">Prohibition of Price Gouging & Hoarding (Ihtikar)</h3>
                    <p className="text-text-secondary text-xs">
                      The Prophet Muhammad (ﷺ) strictly forbade Ihtikar on essential foodstuffs during shortages or peak Ramadan surges.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div className="p-5 rounded-2xl bg-red-500/10 border border-red-500/30 space-y-2">
                    <div className="flex items-center justify-between text-red-300 font-bold">
                      <span>Simulated Unethical Pricing Attempt</span>
                      <span className="bg-red-500/20 px-2 py-0.5 rounded text-[10px]">BLOCKED BY NAZM</span>
                    </div>
                    <p className="text-white font-semibold">Al-Qassim Sukari Dates 1kg (Ramadan Peak)</p>
                    <p className="text-text-secondary">Wholesale Cost Inflation: +2.0% | Attempted Retail Hike: +75% (20 SAR → 35 SAR)</p>
                    <div className="mt-2 p-3 rounded-xl bg-black/40 border border-red-500/20 text-red-300">
                      Shariah Ruling: Raising prices on essential dates by 75% when cost increased by only 2% violates Fiqh al-Mu'amalat fair trade rules. Recommendation blocked.
                    </div>
                  </div>

                  <div className="p-5 rounded-2xl bg-green-500/10 border border-green-500/30 space-y-2">
                    <div className="flex items-center justify-between text-green-300 font-bold">
                      <span>NazmOS Ethical Recommendation</span>
                      <span className="bg-green-500/20 px-2 py-0.5 rounded text-[10px]">APPROVED FAIR TRADE</span>
                    </div>
                    <p className="text-white font-semibold">Al-Qassim Sukari Dates 1kg (Ramadan Peak)</p>
                    <p className="text-text-secondary">Wholesale Cost Inflation: +2.0% | Recommended Retail Price: 21.00 SAR (+5% Margin)</p>
                    <div className="mt-2 p-3 rounded-xl bg-black/40 border border-green-500/20 text-green-300">
                      Shariah Ruling: Pricing aligns with Amanah (Trustworthiness) and Barakah. Protects customer loyalty while maintaining commercial profit.
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "zakat" && (
              <motion.div
                key="zakat"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.3 }}
                className="space-y-6"
              >
                <div className="flex items-center gap-3">
                  <div className="p-3 rounded-2xl bg-green-500/20 text-green-400">
                    <Coins className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white">Retail Ethics Guardrails</h3>
                    <p className="text-text-secondary text-xs">
                      NazmOS warns when essential staples are priced unfairly during high-demand periods.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
                  <div className="space-y-4">
                    <label className="block text-xs font-bold text-text-secondary uppercase">
                      Adjust Net Zakatable Commercial Assets (SAR)
                    </label>
                    <input
                      type="range"
                      min="50000"
                      max="1000000"
                      step="10000"
                      value={zakatBase}
                      onChange={(e) => setZakatBase(Number(e.target.value))}
                      className="w-full accent-green-500"
                    />
                    <div className="flex justify-between font-mono text-sm font-bold text-white">
                      <span>50,000 SAR</span>
                      <span className="text-green-400 text-lg">{formatCurrency(zakatBase)}</span>
                      <span>1,000,000 SAR</span>
                    </div>
                  </div>

                  <div className="p-6 rounded-2xl bg-green-500/10 border border-green-500/30 space-y-3 text-center">
                    <span className="text-xs font-bold uppercase tracking-wider text-green-400">Illustrative Guardrail Impact</span>
                    <p className="text-4xl font-black text-white font-mono">
                      {formatCurrency(zakatBase * 0.02)}
                    </p>
                    <p className="text-[11px] text-text-secondary">
                      Illustrative only: formal religious, tax, or legal review is outside the core Retail Recovery product.
                    </p>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "halal" && (
              <motion.div
                key="halal"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.3 }}
                className="space-y-6"
              >
                <div className="flex items-center gap-3">
                  <div className="p-3 rounded-2xl bg-green-500/20 text-green-400">
                    <HeartHandshake className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white">Automated Halal & SFDA SKU Verification</h3>
                    <p className="text-text-secondary text-xs">
                      Zero tolerance for prohibited ingredients (alcohol, pork derivatives, non-Halal gelatin). Protects store licensing.
                    </p>
                  </div>
                </div>

                <div className="bg-black/40 rounded-2xl p-4 border border-white/5 space-y-3 font-mono text-xs">
                  <div className="flex items-center justify-between p-3 rounded-xl bg-green-500/10 border border-green-500/20 text-green-300">
                    <span>SKU: BEV-MALT-01 (Almarai Apple Malt Drink 330ml)</span>
                    <span className="font-bold">0% Alcohol / SFDA Halal Verified</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-xl bg-green-500/10 border border-green-500/20 text-green-300">
                    <span>SKU: DAT-SUK-05 (Al-Qassim Sukari Premium Dates 5kg)</span>
                    <span className="font-bold">100% Halal / Local Agriculture</span>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Bottom Navigation */}
      <div className="flex items-center justify-between pt-8 border-t border-white/10 mt-8">
        <button
          onClick={prevStep}
          className="flex items-center gap-2 px-6 py-3 rounded-xl bg-white/5 hover:bg-white/10 text-white font-semibold text-sm transition-all"
        >
          <ArrowLeft className="w-4 h-4" /> Previous Step
        </button>
        <button
          onClick={nextStep}
          className="flex items-center gap-2 px-8 py-3 rounded-xl bg-white text-black hover:bg-white/90 font-bold text-sm shadow-xl transition-all hover:scale-105"
        >
          Next: Conversion & Licensing <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
