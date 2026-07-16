"use client";

import { motion } from "framer-motion";
import { TrendingUp, AlertTriangle, Package, Zap, Brain, MessageSquare } from "lucide-react";
import { RevealOnScroll } from "./RevealOnScroll";

const features = [
  {
    icon: TrendingUp,
    title: "Demand Forecasting",
    description: "Prophet-powered sales forecasting with Ramadan / Eid / National Day seasonality. Plan orders weeks ahead.",
  },
  {
    icon: AlertTriangle,
    title: "Smart Stock Alerts",
    description: "Never run out of stock. Get alerts before items run low, based on your actual sales velocity. Email & in-app.",
  },
  {
    icon: Package,
    title: "Dead Stock Detection",
    description: "Identify slow-moving items and free up stuck capital. SAR amounts, not guesses.",
  },
  {
    icon: Zap,
    title: "CSV / POS Ready",
    description: "Import your POS or cashier CSV directly. Column mapper saves your layout permanently.",
  },
  {
    icon: Brain,
    title: "100% On-Prem",
    description: "Runs on YOUR server in Saudi. No cloud, no monthly fees, PDPL compliant. You own all data.",
  },
  {
    icon: MessageSquare,
    title: "Arabic / English",
    description: "Full RTL support, SAR currency, Asia/Riyadh timezone. Built for Saudi retail, not imported.",
  },
];

export function FeatureSection() {
  return (
    <section className="py-24 px-4 bg-bg-primary relative">
      <div className="container mx-auto max-w-6xl">
        <RevealOnScroll>
          <div className="text-center mb-16">
            <h2 className="font-serif text-4xl md:text-5xl font-normal mb-4 text-text-primary">
              Everything you need to run smarter
            </h2>
            <p className="text-lg text-text-secondary max-w-2xl mx-auto">
              NazmOS handles the complexity so you can focus on what matters — running your store.
            </p>
          </div>
        </RevealOnScroll>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-px bg-border-primary">
          {features.map((feature, index) => (
            <RevealOnScroll key={feature.title} delay={index * 0.1}>
              <FeatureCard {...feature} />
            </RevealOnScroll>
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof Brain;
  title: string;
  description: string;
}) {
  return (
    <motion.div
      whileHover={{ backgroundColor: "rgba(255,255,255,0.02)" }}
      transition={{ duration: 0.2 }}
      className="group p-8 bg-bg-secondary border border-transparent"
    >
      <div className="w-12 h-12 flex items-center justify-center mb-5 bg-bg-tertiary border border-border-primary">
        <Icon className="w-5 h-5 text-accent-primary" />
      </div>
      <h3 className="text-lg font-medium mb-2 text-text-primary">{title}</h3>
      <p className="text-text-secondary leading-relaxed text-sm">{description}</p>
    </motion.div>
  );
}
