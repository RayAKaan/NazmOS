"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/Card";
import { ArrowRight, Shield, CheckCircle, FileText, Building2 } from "lucide-react";

export function DemoCompliance() {
  const { nextStep } = useDemoEngine();
  const { t } = useI18n();

  const items = [
    { icon: Shield, color: "text-accent-green", bg: "bg-accent-green/10", title: "Recovery Ledger", status: t.demo.compliance.active, statusColor: "text-accent-green" },
    { icon: CheckCircle, color: "text-accent-green", bg: "bg-accent-green/10", title: t.demo.compliance.tax, status: t.demo.compliance.compliant, statusColor: "text-accent-green" },
    { icon: FileText, color: "text-accent-yellow", bg: "bg-accent-yellow/10", title: t.demo.compliance.visa, status: t.demo.compliance.pending, statusColor: "text-accent-yellow" },
    { icon: Building2, color: "text-accent-blue", bg: "bg-accent-blue/10", title: t.demo.compliance.municipal, status: t.demo.compliance.valid, statusColor: "text-accent-green" },
  ];

  return (
    <div className="p-4 md:p-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h2 className="text-xl font-serif font-bold">{t.demo.compliance.title}</h2>
          <p className="text-sm text-text-muted" dir="rtl">{t.demo.compliance.subtitle}</p>
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {items.map((item, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.1 }}
          >
            <Card>
              <CardContent className="p-5">
                <div className="flex items-center gap-4">
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: 0.3 + i * 0.1, type: "spring" }}
                    className={`w-12 h-12 rounded-xl ${item.bg} flex items-center justify-center`}
                  >
                    <item.icon className={`w-6 h-6 ${item.color}`} />
                  </motion.div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-sm">{item.title}</h3>
                    <div className={`text-xs ${item.statusColor} font-medium`}>{item.status}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
