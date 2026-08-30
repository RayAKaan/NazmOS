"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
import { AmbientBackground } from "@/components/ui/AmbientBackground";

type GoalKey = "stockouts" | "dead_stock" | "margins" | "compliance";

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <OnboardingContent />
    </Suspense>
  );
}

function OnboardingContent() {
  const router = useRouter();
  const { t, locale } = useI18n();
  const isAr = locale === "ar";
  const searchParams = useSearchParams();
  const intent = searchParams.get("intent");
  const [step, setStep] = useState(1);
  const [goal, setGoal] = useState<GoalKey | null>(null);

  useEffect(() => {
    // "free-audit" visitors already chose their goal on the landing page —
    // skip the quiz and go straight to connecting data sources.
    if (intent === "free-audit") {
      setStep((s) => Math.max(s, 2));
    }
  }, [intent]);

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
    <div className="min-h-screen bg-background flex items-center justify-center p-4 md:p-6 relative grain">
      {/* §C: brand-forward screen — slow low-opacity aurora behind the card */}
      <AmbientBackground />
      <div className="relative z-10 w-full max-w-2xl bg-surface border border-border rounded-lg shadow-elevation-3 p-6 md:p-10">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-brand-teal mx-auto flex items-center justify-center text-brand-night font-bold text-2xl mb-3">
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
                className="flex-1 text-center bg-brand-teal text-brand-night py-3 rounded-xl font-medium hover:bg-brand-teal-light transition-colors"
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
                Example preview — what an insight looks like once your files are analyzed. No data is processed at this step.
              </p>
            </div>

            <div className="rounded-xl border border-brand-teal/30 bg-brand-teal/5 p-5 space-y-3">
              <div className="flex items-center gap-2 text-brand-teal-light text-sm font-semibold">
                <CheckCircle2 className="w-4 h-4" />
                {goal === "stockouts" && "Reorder a few fast-movers before they run out this week — real numbers appear after your first audit."}
                {goal === "dead_stock" && "Free up cash tied in slow-selling items — real SAR amounts appear after your first audit."}
                {goal === "margins" && "Review SKUs where shelf price no longer covers cost — real deltas appear after your first audit."}
                {goal === "compliance" && "Keep your VAT return clean — real gaps appear after your first audit."}
                {!goal && "Insight previews appear here once your first audit is complete."}
              </div>
              <p className="text-sm text-text-secondary">
                After your first real audit, ask Nazm Copilot to explain any recommendation, approve actions, or generate a plan.
              </p>
            </div>

            <button
              onClick={next}
              className="w-full bg-brand-teal text-brand-night py-3 rounded-xl font-medium hover:bg-brand-teal-light transition-colors flex items-center justify-center gap-2"
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
              className="w-full bg-brand-teal text-brand-night py-3 rounded-xl font-medium hover:bg-brand-teal-light transition-colors"
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
