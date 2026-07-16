"use client";

import { motion } from "framer-motion";
import { useDemoEngine } from "@/lib/demo-engine";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/Card";
import { DEMO_SUPPLIERS } from "@/lib/demo-data";
import { ArrowRight, Star, Clock, Truck, Phone } from "lucide-react";

export function DemoSuppliers() {
  const { nextStep } = useDemoEngine();
  const { t, locale } = useI18n();

  return (
    <div className="p-4 md:p-6 space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h2 className="text-xl font-serif font-bold">{t.demo.suppliers.title}</h2>
          <p className="text-sm text-text-muted" dir="rtl">{t.demo.suppliers.subtitle}</p>
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
        {DEMO_SUPPLIERS.map((supplier, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.1 }}
          >
            <Card className="h-full">
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-semibold" dir="rtl">{supplier.name_ar}</h3>
                    <p className="text-xs text-text-muted">{supplier.name_en}</p>
                  </div>
                  <div className="flex items-center gap-1 text-accent-yellow">
                    <Star className="w-4 h-4 fill-current" />
                    <span className="text-sm font-medium">{supplier.lead_time_days}d</span>
                  </div>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-text-secondary">
                    <Clock className="w-4 h-4" />
                    <span>{supplier.lead_time_days} {locale === "ar" ? "أيام" : "days"}</span>
                  </div>
                  <div className="flex items-center gap-2 text-text-secondary">
                    <Truck className="w-4 h-4" />
                    <span>{supplier.total_shops_ordering} shops</span>
                  </div>
                  <div className="flex items-center gap-2 text-text-secondary">
                    <Phone className="w-4 h-4" />
                    <span>{supplier.phone}</span>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1">
                  <span className="text-xs px-2 py-1 bg-bg-secondary rounded-full text-text-muted">
                    {supplier.category}
                  </span>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
