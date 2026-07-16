"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { Sparkles, ArrowRight, ArrowLeft, RefreshCw, Zap, TrendingUp, AlertTriangle, CheckCircle2, Building2 } from "lucide-react";

export function DemoOrchestrator() {
  const { nextStep, prevStep } = useDemoEngine();
  const [rebalancingDone, setRebalancingDone] = useState(false);
  const [priceApproved, setPriceApproved] = useState(false);

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
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-blue/10 border border-accent-blue/30 text-accent-blue text-xs font-semibold uppercase tracking-wider mb-3 shadow-[0_0_15px_rgba(59,130,246,0.3)]">
              <Sparkles className="w-3.5 h-3.5 animate-pulse" /> Universal Agentic Core (v3.0)
            </div>
            <h1 className="text-3xl md:text-4xl font-black tracking-tight bg-gradient-to-r from-white via-white/90 to-white/60 bg-clip-text text-transparent">
              Location-Aware Stock Orchestration & Proactive Profit Shield
            </h1>
            <p className="text-text-secondary text-sm md:text-base mt-2 max-w-3xl">
              NazmOS connects all branch ledgers. Watch it automatically rebalance surplus inventory across cities and proactively shield retail margins against wholesale cost hikes.
            </p>
          </div>
        </motion.div>

        {/* 2-Column Vibe UI Glassmorphism Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Card 1: Inter-Branch Stock Rebalancing */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="relative overflow-hidden rounded-3xl bg-surface/80 backdrop-blur-xl border border-white/10 p-6 md:p-8 flex flex-col justify-between shadow-2xl hover:border-accent-blue/40 transition-all group"
          >
            <div className="absolute -right-20 -top-20 w-60 h-60 bg-accent-blue/10 rounded-full blur-3xl pointer-events-none group-hover:bg-accent-blue/20 transition-all" />

            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-accent-blue flex items-center gap-1.5">
                  <Building2 className="w-4 h-4" /> Multi-Location Intelligence
                </span>
                <span className="text-xs bg-green-500/20 text-green-400 border border-green-500/30 px-2.5 py-1 rounded-full font-mono font-semibold">
                  0% External Purchasing Cost
                </span>
              </div>

              <div>
                <h3 className="text-xl font-bold text-white">Inter-Branch Autonomous Transfer</h3>
                <p className="text-text-secondary text-xs mt-1">
                  Instead of spending capital ordering new stock, NazmOS detects overstocked branches and routes stock internally.
                </p>
              </div>

              {/* Visual Scenario */}
              <div className="bg-black/40 rounded-2xl p-4 border border-white/5 space-y-4">
                <div className="flex items-center justify-between text-xs">
                  <div className="p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 w-[45%]">
                    <p className="font-bold text-white">Branch 1: North Riyadh</p>
                    <p className="text-[11px] mt-0.5">Ethiopian Coffee Beans</p>
                    <p className="text-red-400 font-mono font-bold mt-1">68 Days Supply (Surplus)</p>
                  </div>

                  <motion.div
                    animate={{ x: rebalancingDone ? [0, 10, 0] : 0 }}
                    transition={{ repeat: Infinity, duration: 1.5 }}
                    className="text-accent-blue font-bold flex flex-col items-center text-[10px]"
                  >
                    <RefreshCw className={`w-5 h-5 mb-1 ${rebalancingDone ? "animate-spin text-green-400" : ""}`} />
                    {rebalancingDone ? "Transferred 40 Bags" : "Transfer Route"}
                  </motion.div>

                  <div className="p-2.5 rounded-xl bg-yellow-500/10 border border-yellow-500/20 text-yellow-300 w-[45%]">
                    <p className="font-bold text-white">Branch 2: Buraidah Qassim</p>
                    <p className="text-[11px] mt-0.5">Ethiopian Coffee Beans</p>
                    <p className="text-yellow-400 font-mono font-bold mt-1">3 Days Supply (Stockout!)</p>
                  </div>
                </div>

                <AnimatePresence>
                  {rebalancingDone && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      className="p-3 rounded-xl bg-green-500/10 border border-green-500/30 text-green-400 text-xs flex items-center gap-2 font-medium"
                    >
                      <CheckCircle2 className="w-4 h-4 shrink-0 text-green-400" />
                      <span>Saved 1,440 SAR in capital tie-up. Zero supplier PO executed!</span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            <button
              onClick={() => setRebalancingDone(!rebalancingDone)}
              className="mt-6 w-full py-3 px-4 rounded-xl bg-gradient-to-r from-accent-blue to-blue-600 hover:from-blue-600 hover:to-accent-blue text-white font-bold text-sm shadow-[0_4px_20px_rgba(59,130,246,0.4)] transition-all flex items-center justify-center gap-2 active:scale-[0.98]"
            >
              <Zap className="w-4 h-4" />
              {rebalancingDone ? "Reset Simulation" : "Simulate Autonomous Transfer"}
            </button>
          </motion.div>

          {/* Card 2: Proactive Profit Shield */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="relative overflow-hidden rounded-3xl bg-surface/80 backdrop-blur-xl border border-white/10 p-6 md:p-8 flex flex-col justify-between shadow-2xl hover:border-accent-purple/40 transition-all group"
          >
            <div className="absolute -left-20 -bottom-20 w-60 h-60 bg-accent-purple/10 rounded-full blur-3xl pointer-events-none group-hover:bg-accent-purple/20 transition-all" />

            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-accent-purple flex items-center gap-1.5">
                  <TrendingUp className="w-4 h-4" /> Real-Time Margin Guard
                </span>
                <span className="text-xs bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2.5 py-1 rounded-full font-mono font-semibold">
                  Active Interrogation
                </span>
              </div>

              <div>
                <h3 className="text-xl font-bold text-white">Proactive Wholesale Cost Alert</h3>
                <p className="text-text-secondary text-xs mt-1">
                  When supplier invoice OCR detects price inflation, NazmOS auto-calculates the exact shelf price adjustment needed.
                </p>
              </div>

              {/* Alert Simulation Box */}
              <div className="bg-black/40 rounded-2xl p-4 border border-white/5 space-y-3 text-xs">
                <div className="flex items-center justify-between pb-2 border-b border-white/5">
                  <span className="text-white font-semibold flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4 text-yellow-400" /> Almarai Fresh Cream 1L
                  </span>
                  <span className="text-red-400 font-mono font-bold">Margin Drop: 22% → 17.5%</span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-text-secondary">
                  <div>
                    <span className="text-[10px] uppercase text-text-muted">Wholesale Cost Hike</span>
                    <p className="font-mono text-white font-semibold">14.00 SAR → 14.85 SAR</p>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase text-text-muted">Recommended Shelf Price</span>
                    <p className="font-mono text-green-400 font-bold">18.50 SAR (+0.50 SAR)</p>
                  </div>
                </div>

                <AnimatePresence>
                  {priceApproved ? (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="p-3 rounded-xl bg-green-500/10 border border-green-500/30 text-green-400 text-xs flex items-center gap-2 font-medium"
                    >
                      <CheckCircle2 className="w-4 h-4 shrink-0 text-green-400" />
                      <span>Shelf price updated via POS webhook. Restored 320 SAR/mo net profit!</span>
                    </motion.div>
                  ) : (
                    <div className="p-2.5 rounded-xl bg-yellow-500/10 border border-yellow-500/20 text-yellow-300 text-[11px]">
                      Awaiting your WhatsApp button confirmation: [Approve Price Adjustment]
                    </div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            <button
              onClick={() => setPriceApproved(!priceApproved)}
              className="mt-6 w-full py-3 px-4 rounded-xl bg-gradient-to-r from-accent-purple to-purple-600 hover:from-purple-600 hover:to-accent-purple text-white font-bold text-sm shadow-[0_4px_20px_rgba(168,85,247,0.4)] transition-all flex items-center justify-center gap-2 active:scale-[0.98]"
            >
              <CheckCircle2 className="w-4 h-4" />
              {priceApproved ? "Reset Simulation" : "Approve Margin Shield Adjustment"}
            </button>
          </motion.div>
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
          Next: Pilot LOI <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
