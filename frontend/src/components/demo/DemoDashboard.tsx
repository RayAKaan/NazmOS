"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/Card";
import { KPICard } from "@/components/dashboard/KPICard";
import { AlertSection } from "@/components/dashboard/AlertSection";
import { SalesChart } from "@/components/dashboard/SalesChart";
import { DEMO_SUMMARY, DEMO_ALERTS, DEMO_SALES_TREND } from "@/lib/demo-data";
import { formatCurrency } from "@/lib/utils";
import { Play } from "lucide-react";

export function DemoDashboard() {
  const { nextStep } = useDemoEngine();
  const { t } = useI18n();

  const kpis = [
    { label: t.dashboard.todaySales, value: formatCurrency(DEMO_SUMMARY.today.sales), change: `+${DEMO_SUMMARY.comparison.sales_change_percent}%`, positive: true },
    { label: t.dashboard.thisMonth, value: formatCurrency(DEMO_SUMMARY.this_month.sales), change: `+${DEMO_SUMMARY.comparison.sales_change_percent}%`, positive: true },
    { label: t.dashboard.profit, value: formatCurrency(DEMO_SUMMARY.today.profit), change: `+${DEMO_SUMMARY.comparison.profit_change_percent}%`, positive: true },
    { label: t.dashboard.healthScore, value: `${DEMO_SUMMARY.health_score}/100`, change: "Healthy", positive: true },
  ];

  return (
    <div className="p-4 md:p-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h2 className="text-xl font-serif font-bold">{t.demo.dashboard.title}</h2>
          <p className="text-sm text-text-muted">{t.demo.dashboard.subtitle}</p>
        </div>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={nextStep}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-accent-blue to-accent-purple text-white text-sm font-medium rounded-lg shadow-lg shadow-accent-blue/20"
        >
          <Play className="w-4 h-4" />
          {t.demo.dashboard.seeLive}
        </motion.button>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        {kpis.map((kpi, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 + i * 0.1 }}
          >
            <Card>
              <CardContent className="p-4">
                <div className="text-sm text-text-muted">{kpi.label}</div>
                <div className="text-2xl font-bold font-mono">{kpi.value}</div>
                <div className="text-xs text-accent-green mt-1">{kpi.change}</div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.5 }}
        >
          <Card>
            <CardContent className="p-4">
              <h3 className="font-semibold mb-4">{t.dashboard.salesTrend}</h3>
              <SalesChart data={DEMO_SALES_TREND} isLoading={false} />
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.6 }}
        >
          <AlertSection alerts={{ alerts: DEMO_ALERTS }} isLoading={false} />
        </motion.div>
      </div>
    </div>
  );
}
