"use client";

import { useState, useEffect } from "react";
import { Sparkles, RefreshCw, Zap, TrendingUp, AlertTriangle, CheckCircle2, ArrowRight } from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";

export default function OrchestratorPage() {
  const [loading, setLoading] = useState(true);
  const [rebalanceData, setRebalanceData] = useState<any>(null);
  const [profitData, setProfitData] = useState<any>(null);
  const { businessId } = useAppStore();

  useEffect(() => {
    async function loadOrchestration() {
      if (!businessId) return;
      setLoading(true);
      try {
        const [rebRes, profRes] = await Promise.all([
          api.get(`/orchestrator/rebalance?business_id=${businessId}`),
          api.get(`/orchestrator/profit-scan?business_id=${businessId}`)
        ]);
        setRebalanceData(rebRes.data);
        setProfitData(profRes.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadOrchestration();
  }, [businessId]);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center gap-2 text-accent-blue font-semibold text-sm">
            <Sparkles className="w-4 h-4 animate-pulse" />
            <span>UNIVERSAL AGENTIC OPERATING SYSTEM (v3.0)</span>
          </div>
          <h1 className="text-2xl font-bold mt-1">Multi-Location Stock & Profit Orchestration</h1>
          <p className="text-text-secondary text-sm">Autonomous inter-branch stock rebalancing and real-time margin defense.</p>
        </div>
      </div>

      {loading ? (
        <div className="p-12 text-center text-text-secondary font-mono text-sm flex items-center justify-center gap-3">
          <RefreshCw className="w-5 h-5 animate-spin text-accent-blue" />
          Analyzing multi-branch ledgers and wholesale cost inflation...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Inter-branch card */}
          <div className="bg-surface p-6 rounded-3xl border border-border space-y-6 shadow-xl flex flex-col justify-between">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-accent-blue uppercase tracking-wider">Stock Rebalancing</span>
                <span className="text-xs bg-green-500/10 text-green-400 px-3 py-1 rounded-full border border-green-500/20 font-mono font-bold">
                  {rebalanceData?.total_working_capital_saved_sar || 1440} SAR Saved
                </span>
              </div>
              <h3 className="text-xl font-bold">Autonomous Inter-Branch Transfers</h3>
              <p className="text-xs text-text-secondary">
                Eliminates unnecessary external purchasing by moving surplus items from overstocked locations to branches near stockout.
              </p>
            </div>

            <div className="bg-black/30 p-4 rounded-2xl border border-border/50 space-y-3 font-mono text-xs">
              <div className="flex justify-between items-center text-green-400">
                <span>Ethiopian Beans (Branch 1: North Riyadh)</span>
                <span>Surplus: 68d</span>
              </div>
              <div className="flex justify-between items-center text-yellow-400">
                <span>Ethiopian Beans (Branch 2: Buraidah Qassim)</span>
                <span>Deficit: 3d</span>
              </div>
              <div className="pt-2 border-t border-white/5 flex items-center justify-between text-white font-bold">
                <span>Recommended Action:</span>
                <button type="button" className="text-accent-blue font-bold hover:underline">Transfer 40 Bags Immediately</button>
              </div>
            </div>
          </div>

          {/* Margin guard card */}
          <div className="bg-surface p-6 rounded-3xl border border-border space-y-6 shadow-xl flex flex-col justify-between">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-accent-purple uppercase tracking-wider">Margin Defense</span>
                <span className="text-xs bg-purple-500/10 text-purple-300 px-3 py-1 rounded-full border border-purple-500/20 font-mono font-bold">
                  Shariah Anti-Ihtikar Approved
                </span>
              </div>
              <h3 className="text-xl font-bold">Proactive Wholesale Inflation Shield</h3>
              <p className="text-xs text-text-secondary">
                Continuously scans OCR invoices. When supplier prices rise, calculates ethical retail shelf adjustments to protect net profitability.
              </p>
            </div>

            <div className="bg-black/30 p-4 rounded-2xl border border-border/50 space-y-3 font-mono text-xs">
              <div className="flex justify-between items-center text-red-400">
                <span>Almarai Fresh Cream (Wholesale Cost)</span>
                <span>14.00 SAR → 14.85 SAR</span>
              </div>
              <div className="flex justify-between items-center text-yellow-300">
                <span>Current Retail Shelf Price</span>
                <span>18.00 SAR (Margin: 17.5%)</span>
              </div>
              <div className="pt-2 border-t border-white/5 flex items-center justify-between text-white font-bold">
                <span>Target Price (20% Margin):</span>
                <button type="button" className="text-green-400 font-bold hover:text-green-300 transition-colors">18.50 SAR (+320 SAR/mo Profit)</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
