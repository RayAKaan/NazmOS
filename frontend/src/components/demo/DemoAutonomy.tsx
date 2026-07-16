"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/Card";
import { ArrowRight, Shield, Zap, Clock, AlertTriangle, CheckCircle, Lock } from "lucide-react";

export function DemoAutonomy() {
  const { nextStep } = useDemoEngine();
  const { t } = useI18n();

  const rules = [
    { icon: AlertTriangle, color: "text-yellow-400", bg: "bg-yellow-500/10", title: t.autonomy.restocking, desc: "Auto-reorder when stock drops below reorder level" },
    { icon: Shield, color: "text-accent-green", bg: "bg-accent-green/10", title: t.autonomy.priceIncrease, desc: "Dynamic pricing based on demand and competition" },
    { icon: Clock, color: "text-accent-blue", bg: "bg-accent-blue/10", title: t.autonomy.expiryAlerts, desc: "FEFO alerts for items approaching expiry" },
    { icon: CheckCircle, color: "text-accent-green", bg: "bg-accent-green/10", title: t.autonomy.cashFlow, desc: "Real-time cash position and forecast" },
    { icon: Lock, color: "text-accent-purple", bg: "bg-accent-purple/10", title: t.autonomy.staffing, desc: "Staff scheduling optimization" },
    { icon: Zap, color: "text-accent-yellow", bg: "bg-accent-yellow/10", title: t.autonomy.priceDecrease, desc: "Clearance pricing for dead stock" },
  ];

  return (
    <div className="p-4 md:p-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h2 className="text-xl font-serif font-bold">{t.demo.autonomy.title}</h2>
          <p className="text-sm text-text-muted" dir="rtl">{t.demo.autonomy.subtitle}</p>
        </div>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={nextStep}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-accent-blue to-accent-purple text-white text-sm font-medium rounded-lg shadow-lg shadow-accent-blue/20"
        >
          {t.next}
          <ArrowRight className="w-4 h-4" />
        </motion.button>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {rules.map((rule, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.1 }}
          >
            <Card className="h-full">
              <CardContent className="p-5">
                <div className={`w-10 h-10 rounded-lg ${rule.bg} flex items-center justify-center mb-3`}>
                  <rule.icon className={`w-5 h-5 ${rule.color}`} />
                </div>
                <h3 className="font-semibold text-sm mb-1">{rule.title}</h3>
                <p className="text-xs text-text-muted">{rule.desc}</p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
