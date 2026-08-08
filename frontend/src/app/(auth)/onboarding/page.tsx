"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import {
  Package,
  TrendingDown,
  DollarSign,
  ShieldCheck,
  Upload,
  ArrowRight,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";

type GoalKey = "stockouts" | "dead_stock" | "margins" | "compliance";

export default function OnboardingPage() {
  const router = useRouter();
  const { t, locale } = useI18n();
  const isAr = locale === "ar";
  const [step, setStep] = useState(1);
  const [goal, setGoal] = useState<GoalKey | null>(null);

  const goals: { key: GoalKey; label: string; icon: React.ElementType; description: string }[] = [
    {
      key: "stockouts",
      label: t.onboarding.goalStockouts,
      icon: Package,
      description: "Get alerts before you run out of best-selling items.",
    },
    {
      key: "dead_stock",
      label: t.onboarding.goalDeadStock,
      icon: TrendingDown,
      description: "Identify and clear slow-moving inventory fast.",
    },
    {
      key: "margins",
      label: t.onboarding.goalMargins,
      icon: DollarSign,
      description: "Spot margin leakage and price better than competitors.",
    },
    {
      key: "compliance",
      label: t.onboarding.goalCompliance,
      icon: ShieldCheck,
      description: "Stay Saudi tax authority-ready and keep your books clean.",
    },
  ];

  const steps = [
    { id: 1, label: t.onboarding.step1 },
    { id: 2, label: t.onboarding.step2 },
    { id: 3, label: t.onboarding.step3 },
    { id: 4, label: t.onboarding.step4 },
  ];

  const next = () => setStep((s) => Math.min(s + 1, 4));
  const prev = () => setStep((s) => Math.max(s - 1, 1));

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 md:p-6">
      <div className="w-full max-w-2xl bg-surface border border-border rounded-2xl p-6 md:p-10">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-brand-teal mx-auto flex items-center justify-center text-black font-bold text-2xl mb-3">
            ن
          </div>
          <h1 className="text-2xl md:text-3xl font-bold">{t.onboarding.welcome}</h1>
          <p className="text-text-muted mt-1">{t.onboarding.subtitle}</p>
        </div>

        {step === 1 && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold text-center">{t.onboarding.goalQuestion}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {goals.map((g) => {
                const Icon = g.icon;
                const selected = goal === g.key;
                return (
                  <button
                    key={g.key}
                    onClick={() => {
                      setGoal(g.key);
                      next();
                    }}
                    className={cn(
                      "flex flex-col items-start gap-2 p-4 rounded-xl border text-left transition-all",
                      selected
                        ? "border-brand-teal bg-brand-teal/10 text-text-primary"
                        : "border-border bg-bg-secondary text-text-secondary hover:border-brand-teal/30 hover:bg-brand-teal/5"
                    )}
                  >
                    <Icon className={cn("w-5 h-5", selected ? "text-brand-teal" : "text-text-muted")} />
                    <span className="font-semibold">{g.label}</span>
                    <span className="text-xs leading-5">{g.description}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6">
            <div className="text-center">
              <h2 className="text-lg font-semibold">{t.onboarding.uploadData}</h2>
              <p className="text-sm text-text-muted mt-1">
                CSV / Excel from your POS or cashier export. We auto-detect columns.
              </p>
            </div>

            <div className="rounded-xl border border-dashed border-border bg-bg-secondary p-8 text-center">
              <Upload className="w-8 h-8 text-brand-teal mx-auto mb-3" />
              <p className="font-medium">Drag a file here or click to upload</p>
              <p className="text-xs text-text-muted mt-1">
                product_name, quantity, price, date — all data stays local
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/upload"
                className="flex-1 text-center bg-brand-teal text-black py-3 rounded-xl font-medium hover:bg-brand-teal-light transition-colors"
              >
                Go to Upload →
              </Link>
              <button
                onClick={next}
                className="flex-1 border border-border bg-bg-secondary text-text-primary py-3 rounded-xl font-medium hover:bg-bg-tertiary transition-colors"
              >
                Skip — I uploaded already
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6">
            <div className="text-center">
              <h2 className="text-lg font-semibold">{t.onboarding.firstInsight}</h2>
              <p className="text-sm text-text-muted mt-1">
                Nazm is analyzing your data. Here is a preview of what you will see.
              </p>
            </div>

            <div className="rounded-xl border border-brand-teal/30 bg-brand-teal/5 p-5 space-y-3">
              <div className="flex items-center gap-2 text-brand-teal-light text-sm font-semibold">
                <CheckCircle2 className="w-4 h-4" />
                {goal === "stockouts" && "3 items are running low and need reorder this week."}
                {goal === "dead_stock" && "SAR 12,400 is tied up in items that have not sold in 60 days."}
                {goal === "margins" && "2 suppliers raised prices; 5 SKUs need shelf-price review."}
                {goal === "compliance" && "Your VAT report is 98% complete — 2 invoices need categorization."}
                {!goal && "Your first intelligence summary is ready."}
              </div>
              <p className="text-sm text-text-secondary">
                You can ask Nazm Copilot to explain any recommendation, approve actions, or generate a plan.
              </p>
            </div>

            <button
              onClick={next}
              className="w-full bg-brand-teal text-black py-3 rounded-xl font-medium hover:bg-brand-teal-light transition-colors flex items-center justify-center gap-2"
            >
              {t.onboarding.openDashboard} <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-6 text-center">
            <div className="w-16 h-16 rounded-full bg-brand-teal/15 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8 text-brand-teal" />
            </div>
            <h2 className="text-xl font-bold">You are all set</h2>
            <p className="text-sm text-text-muted">
              Your dashboard is ready. Nazm will keep watching your inventory 24/7.
            </p>
            <button
              onClick={() => router.push("/dashboard")}
              className="w-full bg-brand-teal text-black py-3 rounded-xl font-medium hover:bg-brand-teal-light transition-colors"
            >
              {t.onboarding.openDashboard}
            </button>
          </div>
        )}

        <div className="mt-10">
          <div className="flex items-center justify-between mb-2">
            {steps.map((s) => (
              <div
                key={s.id}
                className={cn(
                  "flex-1 text-center text-xs font-medium transition-colors",
                  s.id <= step ? "text-brand-teal" : "text-text-muted"
                )}
              >
                {s.label}
              </div>
            ))}
          </div>
          <div className="flex gap-1">
            {steps.map((s) => (
              <div
                key={s.id}
                className={cn(
                  "h-1.5 flex-1 rounded-full transition-colors",
                  s.id <= step ? "bg-brand-teal" : "bg-border"
                )}
              />
            ))}
          </div>
          {step > 1 && step < 4 && (
            <button
              onClick={prev}
              className="mt-4 text-sm text-text-muted hover:text-text-primary underline"
            >
              {isAr ? "رجوع" : "Back"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
