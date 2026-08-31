"use client";

import { useState } from "react";
import { Scale, CheckCircle2, AlertTriangle, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

interface ComparisonOption {
  name: string;
  expected_recovery_sar?: number | null;
  low_sar: number;
  high_sar: number;
  confidence: string;
  estimate_only: boolean;
  evidence?: Record<string, unknown>;
  recommended?: boolean;
}

interface DecisionComparisonProps {
  productName: string;
  options: ComparisonOption[];
  recommendation?: string;
  className?: string;
}

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return `SAR ${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function confidenceColor(confidence: string) {
  if (confidence === "HIGH") return "text-brand-green bg-brand-green/10 border-brand-green/25";
  if (confidence === "MEDIUM") return "text-brand-amber bg-brand-amber/10 border-brand-amber/25";
  return "text-brand-cream/60 bg-brand-cream/10 border-brand-cream/15";
}

export function DecisionComparison({ productName, options, recommendation, className }: DecisionComparisonProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (options.length === 0) return null;

  return (
    <section className={cn("rounded-3xl border border-border bg-surface p-6", className)}>
      <div className="flex items-center gap-2">
        <Scale className="h-5 w-5 text-brand-amber" />
        <h2 className="text-xl font-bold">Decision Comparison</h2>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Comparing options for <span className="font-bold text-foreground">{productName}</span>
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {options.map((option, idx) => (
          <div
            key={idx}
            className={cn(
              "relative rounded-2xl border p-4 transition-all",
              option.recommended
                ? "border-brand-green/50 bg-brand-green/5 shadow-md"
                : "border-border bg-brand-night/5 hover:shadow-sm"
            )}
          >
            {option.recommended && (
              <div className="absolute -top-3 left-4 rounded-full bg-brand-green px-3 py-0.5 text-xs font-bold text-brand-night">
                NazmOS Recommends
              </div>
            )}

            <div className="flex items-start justify-between">
              <h3 className="font-bold text-foreground">{option.name}</h3>
              {option.recommended && <CheckCircle2 className="h-5 w-5 text-brand-green" />}
              {!option.recommended && <Minus className="h-4 w-4 text-muted-foreground" />}
            </div>

            <div className="mt-3">
              <div className="text-2xl font-bold text-foreground">
                {option.expected_recovery_sar != null
                  ? money(option.expected_recovery_sar)
                  : `${money(option.low_sar)}–${money(option.high_sar)}`}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">estimated recovery</div>
            </div>

            <div className="mt-3 flex items-center gap-2">
              <span className={cn("rounded-full border px-2 py-0.5 text-xs font-bold", confidenceColor(option.confidence))}>
                {option.confidence}
              </span>
              {option.estimate_only && (
                <span className="rounded-full bg-brand-cream/10 px-2 py-0.5 text-xs font-bold text-muted-foreground">
                  ESTIMATE
                </span>
              )}
            </div>

            {/* Risks */}
            <div className="mt-3 text-xs text-muted-foreground">
              {option.name === "DO NOTHING" && (
                <div className="flex items-start gap-1">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-brand-amber" />
                  <span>Capital remains locked. Risk of further depreciation.</span>
                </div>
              )}
              {option.name === "DISCOUNT" && (
                <div className="flex items-start gap-1">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-brand-amber" />
                  <span>Margin reduction. Potential brand perception impact.</span>
                </div>
              )}
              {option.name === "TRANSFER" && (
                <div className="flex items-start gap-1">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-brand-amber" />
                  <span>Logistics cost. Destination demand required.</span>
                </div>
              )}
            </div>

            {/* Expand evidence */}
            {option.evidence && Object.keys(option.evidence).length > 0 && (
              <>
                <button
                  onClick={() => setExpanded(expanded === option.name ? null : option.name)}
                  className="mt-3 text-xs font-bold text-muted-foreground hover:text-foreground"
                >
                  {expanded === option.name ? "Hide details" : "Show details"}
                </button>
                {expanded === option.name && (
                  <div className="mt-2 rounded-xl bg-brand-night/10 p-2 text-xs text-muted-foreground">
                    {Object.entries(option.evidence).map(([key, value]) => (
                      <div key={key}>
                        <span className="font-bold">{key.replace(/_/g, " ")}:</span>{" "}
                        {typeof value === "number" ? value.toLocaleString() : String(value ?? "—")}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      {recommendation && (
        <div className="mt-4 rounded-xl bg-brand-green/5 p-3 text-sm text-foreground">
          <span className="font-bold">NazmOS recommends:</span> {recommendation}
        </div>
      )}
    </section>
  );
}
