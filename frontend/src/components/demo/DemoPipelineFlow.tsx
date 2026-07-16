"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { 
  Zap, ShieldCheck, Cpu, ArrowRight, ArrowLeft, CheckCircle2, 
  RefreshCw, QrCode, Sparkles, Building2, Coins, Share2, Play
} from "lucide-react";

const PIPELINE_NODES = [
  {
    id: "pos",
    title: "1. Real-Time POS Ingestion",
    title_ar: "الربط المباشر مع نقاط البيع",
    badge: "Foodics / Salla Webhook",
    color: "from-blue-500 to-cyan-500",
    border: "border-blue-500/40",
    icon: Zap,
    desc: "Webhook receives Order #FD-8890 (2x V60 Ethiopian Coffee | 46.00 SAR). Instantly deducts branch inventory across North Riyadh.",
    metricValue: "< 12ms Sync Latency",
  },
  {
    id: "ledger",
    title: "2. Retail Recovery Ledger",
    title_ar: "سجل استرجاع الأرباح",
    badge: "Sales + Inventory Ledger",
    color: "from-green-500 to-emerald-500",
    border: "border-green-500/40",
    icon: QrCode,
    desc: "Records the sale, updates inventory, recalculates days-of-supply, and refreshes Money at Risk for the owner.",
    metricValue: "Ledger Updated",
  },
  {
    id: "agentic",
    title: "3. Universal Agentic Orchestration",
    title_ar: "الذكاء الاصطناعي التشغيلي",
    badge: "Location-Aware Rebalancing",
    color: "from-purple-500 to-indigo-500",
    border: "border-purple-500/40",
    icon: Cpu,
    desc: "Analyzes velocity. Detects surplus stock in North Riyadh (68d supply) vs stockout in Buraidah (3d supply). Recommends inter-branch transfer instead of new PO.",
    metricValue: "1,440 SAR Capital Saved",
  },
  {
    id: "shariah",
    title: "4. Shariah Ethics Guardrails",
    title_ar: "التوافق الشرعي والأخلاقي",
    badge: "Anti-Ihtikar & Halal Guard",
    color: "from-amber-500 to-yellow-500",
    border: "border-amber-500/40",
    icon: ShieldCheck,
    desc: "Audits SKU ingredients (0% alcohol/Haram), blocks unethical price gouging during Ramadan date surges, and calculates 2.5% Zakat base.",
    metricValue: "100% Halal Verified",
  },
  {
    id: "copilot",
    title: "5. Executive WhatsApp Copilot",
    title_ar: "المساعد التنفيذي عبر واتساب",
    badge: "Meta 1,000 Free Tier",
    color: "from-rose-500 to-pink-500",
    border: "border-rose-500/40",
    icon: Share2,
    desc: "Sends interactive approval button [✅ Approve Transfer] directly to owner's WhatsApp in natural Najdi Arabic. Zero app login needed.",
    metricValue: "0 SAR API Cost",
  },
];

export function DemoPipelineFlow() {
  const { nextStep, prevStep } = useDemoEngine();
  const [activeNodeIndex, setActiveNodeIndex] = useState(0);
  const [isRunning, setIsRunning] = useState(false);

  const startAutomatedPipeline = () => {
    setIsRunning(true);
    setActiveNodeIndex(0);
  };

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (isRunning) {
      if (activeNodeIndex < PIPELINE_NODES.length - 1) {
        timer = setTimeout(() => {
          setActiveNodeIndex((prev) => prev + 1);
        }, 2200);
      } else {
        timer = setTimeout(() => {
          setIsRunning(false);
        }, 3000);
      }
    }
    return () => clearTimeout(timer);
  }, [isRunning, activeNodeIndex]);

  const currentNode = PIPELINE_NODES[activeNodeIndex];

  return (
    <div className="min-h-screen pt-24 pb-16 px-4 md:px-8 max-w-6xl mx-auto flex flex-col justify-between">
      <div className="space-y-8">
        {/* Header Section */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6"
        >
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-accent-blue/20 to-accent-purple/20 border border-accent-blue/30 text-white text-xs font-semibold uppercase tracking-wider mb-3 shadow-[0_0_20px_rgba(59,130,246,0.3)]">
              <Sparkles className="w-3.5 h-3.5 text-accent-blue animate-pulse" /> Interactive Architecture Flow
            </div>
            <h1 className="text-3xl md:text-4xl font-black tracking-tight bg-gradient-to-r from-white via-white/90 to-white/60 bg-clip-text text-transparent">
              How NazmOS Works: The End-to-End Autonomous Pipeline
            </h1>
            <p className="text-text-secondary text-sm md:text-base mt-2 max-w-3xl">
              Watch a live transaction pass through all 5 operational intelligence layers in real time—from POS webhook sync and inventory recovery to WhatsApp owner approval.
            </p>
          </div>

          <button
            onClick={startAutomatedPipeline}
            disabled={isRunning}
            className="flex items-center justify-center gap-2 bg-gradient-to-r from-accent-blue to-purple-600 hover:from-purple-600 hover:to-accent-blue text-white px-6 py-3 rounded-2xl font-bold text-sm shadow-[0_4px_25px_rgba(59,130,246,0.4)] transition-all shrink-0 hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            {isRunning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" /> Executing Pipeline...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" /> Run Live Pipeline Simulation
              </>
            )}
          </button>
        </motion.div>

        {/* Pipeline Progress Track */}
        <div className="relative pt-6 pb-2">
          <div className="absolute top-1/2 left-0 right-0 h-1 bg-white/10 -translate-y-1/2 z-0 hidden md:block rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-rose-500"
              initial={{ width: "0%" }}
              animate={{ width: `${(activeNodeIndex / (PIPELINE_NODES.length - 1)) * 100}%` }}
              transition={{ duration: 0.5, ease: "easeInOut" }}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 relative z-10">
            {PIPELINE_NODES.map((node, idx) => {
              const Icon = node.icon;
              const isSelected = activeNodeIndex === idx;
              const isPassed = activeNodeIndex > idx;

              return (
                <button
                  key={node.id}
                  onClick={() => {
                    setIsRunning(false);
                    setActiveNodeIndex(idx);
                  }}
                  className={`flex md:flex-col items-center gap-3 p-3.5 rounded-2xl border transition-all text-left md:text-center ${
                    isSelected
                      ? `bg-surface/90 ${node.border} shadow-[0_0_25px_rgba(59,130,246,0.25)] scale-105`
                      : isPassed
                      ? "bg-surface/50 border-green-500/30 text-white/80"
                      : "bg-surface/30 border-white/5 text-text-muted hover:border-white/20"
                  }`}
                >
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-all ${
                      isSelected
                        ? `bg-gradient-to-br ${node.color} text-white shadow-lg`
                        : isPassed
                        ? "bg-green-500/20 text-green-400 border border-green-500/40"
                        : "bg-white/5 text-text-secondary"
                    }`}
                  >
                    {isPassed ? <CheckCircle2 className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-accent-blue truncate">
                      Node {idx + 1}
                    </div>
                    <div className="text-xs font-bold truncate text-white mt-0.5">{node.title.split(". ")[1]}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Detailed Spotlight Box for Active Node */}
        <AnimatePresence mode="wait">
          <motion.div
            key={currentNode.id}
            initial={{ opacity: 0, scale: 0.98, y: 15 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: -15 }}
            transition={{ duration: 0.3 }}
            className={`rounded-3xl bg-surface/80 backdrop-blur-2xl border ${currentNode.border} p-6 md:p-8 shadow-2xl space-y-6 relative overflow-hidden`}
          >
            <div className={`absolute -right-24 -top-24 w-72 h-72 rounded-full bg-gradient-to-br ${currentNode.color} opacity-15 blur-3xl pointer-events-none`} />

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
              <div className="flex items-center gap-4">
                <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${currentNode.color} flex items-center justify-center text-white shadow-xl shrink-0`}>
                  <currentNode.icon className="w-7 h-7" />
                </div>
                <div>
                  <span className="text-xs font-mono font-bold px-3 py-1 rounded-full bg-white/5 border border-white/10 text-white uppercase tracking-wider">
                    {currentNode.badge}
                  </span>
                  <h2 className="text-2xl font-black text-white mt-2">{currentNode.title}</h2>
                  <p className="text-xs text-text-muted">{currentNode.title_ar}</p>
                </div>
              </div>

              <div className="bg-black/40 px-5 py-3 rounded-2xl border border-white/10 text-center shrink-0">
                <span className="text-[10px] uppercase tracking-wider text-text-muted font-bold block">Runtime Verification Metric</span>
                <span className="text-lg font-mono font-black text-green-400">{currentNode.metricValue}</span>
              </div>
            </div>

            <p className="text-text-secondary text-sm md:text-base leading-relaxed border-t border-white/10 pt-4 relative z-10">
              {currentNode.desc}
            </p>

            {/* Interactive Telemetry Box */}
            <div className="bg-black/50 rounded-2xl p-4 border border-white/5 font-mono text-xs space-y-2.5 relative z-10">
              <div className="flex items-center justify-between pb-2 border-b border-white/5 text-text-muted">
                <span>SYSTEM LOG: NODE_{currentNode.id.toUpperCase()}</span>
                <span className="text-green-400 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-green-400 animate-ping" /> STATUS: OPERATIONAL
                </span>
              </div>
              
              {currentNode.id === "pos" && (
                <div className="space-y-1.5 text-white">
                  <p className="text-blue-300">&gt; POST /api/v1/pos/foodics/webhook [HTTP 200 OK]</p>
                  <p>&gt; Items: [V60 Ethiopian Specialty Coffee x2] | Gross: 46.00 SAR</p>
                  <p className="text-green-400">&gt; Inventory updated: North Riyadh Branch stock reduced by 2 units.</p>
                </div>
              )}

              {currentNode.id === "ledger" && (
                <div className="space-y-1.5 text-white">
                  <p className="text-green-300">&gt; Retail ledger updated: Order FD-8890 | Stock + margin recalculated</p>
                  <p>&gt; Money at Risk refreshed from latest sale and stock movement.</p>
                  <p className="text-emerald-400 break-all">&gt; Weekly Money Report queue updated for owner review.</p>
                </div>
              )}

              {currentNode.id === "agentic" && (
                <div className="space-y-1.5 text-white">
                  <p className="text-purple-300">&gt; Inter-Branch evaluation: North Riyadh (Surplus 68d) vs Buraidah (Stockout 3d).</p>
                  <p>&gt; Action generated: Transfer 40 bags from Riyadh to Buraidah date market store.</p>
                  <p className="text-green-400">&gt; Capital tie-up eliminated: 1,440.00 SAR saved.</p>
                </div>
              )}

              {currentNode.id === "shariah" && (
                <div className="space-y-1.5 text-white">
                  <p className="text-amber-300">&gt; Halal SKU Audit: 100% Clean | 0 Prohibited ingredients detected.</p>
                  <p>&gt; Anti-Ihtikar Guard: Ramadan date wholesale cost +2% -&gt; Retail price increase capped at fair trade 5% margin.</p>
                  <p className="text-yellow-400">&gt; Zakat Liability calculated: 2.5% statutory religious base prepared for 1-click filing.</p>
                </div>
              )}

              {currentNode.id === "copilot" && (
                <div className="space-y-1.5 text-white">
                  <p className="text-pink-300">&gt; WhatsApp Interactive Message sent via Meta Cloud API (+966 5X XXX XXXX).</p>
                  <p>&gt; Owner received audio note &amp; interactive buttons: [✅ Approve Transfer] / [❌ Reject].</p>
                  <p className="text-green-400">&gt; Owner clicked Approve. Purchase order executed autonomously!</p>
                </div>
              )}
            </div>
          </motion.div>
        </AnimatePresence>
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
          Next: Inventory Risk View <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
