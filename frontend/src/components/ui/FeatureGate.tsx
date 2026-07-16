"use client";

import Link from "next/link";
import { ArrowRight, Lock } from "lucide-react";

interface FeatureGateProps {
  feature: string;
  title: string;
  description: string;
  requiredPlan?: string;
}

export function FeatureGate({
  feature,
  title,
  description,
  requiredPlan = "Recovery Pilot",
}: FeatureGateProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center shadow-2xl shadow-black/10">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-400/10 text-amber-300">
        <Lock className="h-5 w-5" />
      </div>
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-amber-300/80">
        Locked feature · {feature}
      </p>
      <h3 className="mt-2 text-lg font-bold text-white">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-white/60">{description}</p>
      <p className="mt-3 text-xs uppercase tracking-[0.2em] text-amber-300">
        Requires {requiredPlan}
      </p>
      <Link
        href="/register?intent=pilot"
        className="mt-5 inline-flex items-center gap-2 rounded-xl bg-amber-300 px-4 py-2 text-sm font-bold text-black transition hover:bg-amber-200"
      >
        Start 30-Day Pilot <ArrowRight className="h-4 w-4" />
      </Link>
    </div>
  );
}
