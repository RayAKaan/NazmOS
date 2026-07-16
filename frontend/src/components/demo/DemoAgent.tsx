"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/Card";
import { ArrowRight, Check, Lightbulb, BarChart3, ShoppingCart } from "lucide-react";

export function DemoAgent() {
  const { nextStep } = useDemoEngine();
  const { t } = useI18n();

  const reasoningSteps = [
    { icon: BarChart3, color: "text-accent-blue", en: "Analyzing 30-day sales trends", ar: "تحليل اتجاهات المبيعات لـ ٣٠ يوم" },
    { icon: Lightbulb, color: "text-accent-yellow", en: "Checking supplier lead times", ar: "فحص أوقات التوصيل من الموردين" },
    { icon: ShoppingCart, color: "text-accent-green", en: "Calculating optimal reorder quantities", ar: "حساب الكميات المثلى لإعادة الطلب" },
  ];

  const actions = [
    { en: "Auto-reorder Almarai Milk × 135 units", ar: "إعادة طلب تلقائية — حليب المراعي × ١٣٥ وحدة" },
    { en: "Switch water supplier for 8% savings", ar: "تبديل مورد المياه لتوفير ٨٪" },
    { en: "Flag 3 items for expiry review", ar: "تحديد ٣ منتجات لمراجعة الصلاحية" },
  ];

  return (
    <div className="p-4 md:p-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h2 className="text-xl font-serif font-bold">{t.demo.agent.title}</h2>
          <p className="text-sm text-text-muted" dir="rtl">{t.demo.agent.subtitle}</p>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-accent-blue/5 to-transparent" />
          <CardContent className="relative p-6">
            <div className="flex items-center gap-3 mb-6">
              <motion.div
                animate={{ scale: [1, 1.1, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
                className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center"
              >
                <span className="text-white text-xl">🤖</span>
              </motion.div>
              <div>
                <h3 className="font-semibold">{t.demo.agent.nazmTitle}</h3>
                <p className="text-xs text-text-muted">{t.agent.confidence}: 94%</p>
              </div>
            </div>
            <div className="space-y-3">
              {reasoningSteps.map((step, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.5 + i * 0.3 }}
                  className="flex items-start gap-3 p-3 rounded-lg bg-bg-primary/50"
                >
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: 0.8 + i * 0.3, type: "spring" }}
                    className="w-5 h-5 rounded-full bg-accent-green/20 flex items-center justify-center mt-0.5 shrink-0"
                  >
                    <Check className="w-3 h-3 text-accent-green" />
                  </motion.div>
                  <div>
                    <div className="font-medium text-sm">{step.en}</div>
                    <div className="text-xs text-text-muted mt-1" dir="rtl">{step.ar}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <h3 className="font-semibold mb-4">{t.demo.agent.actions}</h3>
            <div className="space-y-3">
              {actions.map((action, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 1.5 + i * 0.2 }}
                  className="flex items-center gap-3 p-3 rounded-lg bg-bg-primary/50 border border-border"
                >
                  <div className="w-8 h-8 rounded-lg bg-accent-blue/10 flex items-center justify-center">
                    <Check className="w-4 h-4 text-accent-blue" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{action.en}</div>
                    <div className="text-xs text-text-muted" dir="rtl">{action.ar}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
