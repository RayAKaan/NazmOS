"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/Card";
import { DEMO_INVENTORY } from "@/lib/demo-data";
import { ArrowRight, AlertTriangle, CheckCircle, Package } from "lucide-react";

export function DemoInventory() {
  const { nextStep } = useDemoEngine();
  const { t } = useI18n();

  return (
    <div className="p-4 md:p-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h2 className="text-xl font-serif font-bold">{t.demo.inventory.title}</h2>
          <p className="text-sm text-text-muted" dir="rtl">{t.demo.inventory.subtitle}</p>
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

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-4 font-medium">{t.demo.inventory.product}</th>
                  <th className="text-left p-4 font-medium">{t.demo.inventory.stock}</th>
                  <th className="text-left p-4 font-medium">{t.demo.inventory.status}</th>
                  <th className="text-left p-4 font-medium">{t.demo.inventory.action}</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_INVENTORY.items.map((item, i) => (
                  <motion.tr
                    key={i}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.2 + i * 0.05 }}
                    className="border-b border-border last:border-0"
                  >
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-bg-secondary flex items-center justify-center text-lg">
                          <Package className="w-5 h-5 text-text-muted" />
                        </div>
                        <div>
                          <div className="font-medium" dir="rtl">{item.name_ar}</div>
                          <div className="text-xs text-text-muted">{item.sku}</div>
                        </div>
                      </div>
                    </td>
                    <td className="p-4">
                      <span className={`font-mono font-medium ${item.status === "critical" ? "text-red-400" : item.status === "low" ? "text-yellow-400" : "text-accent-green"}`}>
                        {item.current_stock}
                      </span>
                    </td>
                    <td className="p-4">
                      {item.status === "critical" || item.status === "low" ? (
                        <span className="flex items-center gap-1 text-red-400 text-xs">
                          <AlertTriangle className="w-3 h-3" />
                          {t.demo.inventory.low}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-accent-green text-xs">
                          <CheckCircle className="w-3 h-3" />
                          {t.demo.inventory.ok}
                        </span>
                      )}
                    </td>
                    <td className="p-4 text-xs text-text-muted" dir="rtl">{item.category}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
