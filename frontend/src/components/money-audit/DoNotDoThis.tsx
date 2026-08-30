"use client";

import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface DoNotDoThisProps {
  decisions: {
    id: string;
    title: string;
    description?: string | null;
    action_type: string;
    evidence?: Record<string, unknown>;
    recovery_confidence?: string;
  }[];
  className?: string;
}

/**
 * "ONE THING I WOULD NOT DO" — a key NazmOS differentiator.
 *
 * Finds an action where the system recommends NO ACTION despite the owner
 * potentially being tempted to act. This demonstrates the system's ability
 * to correctly recommend doing nothing.
 */
export function DoNotDoThis({ decisions, className }: DoNotDoThisProps) {
  // Find the best candidate: a suggested action where DO_NOTHING is better
  // Look for seasonal items, items with incoming stock, or items with insufficient data
  const candidates = decisions.filter((d) => {
    const evidence = d.evidence || {};
    const classification = evidence.classification as string;

    // Seasonal items where season may have ended
    if (classification === "SEASONAL") return true;

    // Items with confirmed inbound (don't reorder)
    if (evidence.confirmed_inbound_qty && (evidence.confirmed_inbound_qty as number) > 0) return true;

    // Items classified as NEW (insufficient data)
    if (classification === "NEW") return true;

    return false;
  });

  if (candidates.length === 0) return null;

  const pick = candidates[0];
  const evidence = pick.evidence || {};
  const classification = evidence.classification as string;

  let reason = "";
  if (classification === "SEASONAL") {
    reason = `This is a seasonal item. Although recent demand may appear elevated, the seasonal pattern suggests waiting before committing capital. Acting now could result in excess inventory once the season ends.`;
  } else if (evidence.confirmed_inbound_qty && (evidence.confirmed_inbound_qty as number) > 0) {
    const inbound = Number(evidence.confirmed_inbound_qty);
    const ghost = Boolean(evidence.ghost_po_risk);
    reason = ghost
      ? `There is ${inbound} confirmed inbound unit${inbound === 1 ? "" : "s"} already on order, though one or more of those purchase orders appears to be overdue (ghost-PO risk). Before adding fresh stock, verify the supplier will actually deliver — a ghost PO should not be cashed a second time.`
      : `There is ${inbound} confirmed inbound unit${inbound === 1 ? "" : "s"} on the way. Adding more stock now would risk overstocking and tying up cash unnecessarily.`;
  } else if (classification === "NEW") {
    reason = `This product is too new to have sufficient sales data. The classification is based on limited information. Waiting for more data will lead to a better decision.`;
  } else {
    reason = `Although there appears to be an opportunity, the evidence suggests that taking no action is the better choice right now.`;
  }

  return (
    <section className={cn("rounded-3xl border border-brand-amber/25 bg-brand-amber/5 p-6", className)}>
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-amber/20">
          <AlertTriangle className="h-4 w-4 text-brand-amber" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-text-primary">One Thing I Would Not Do</h2>
          <p className="mt-1 text-sm text-text-secondary">
            Sometimes the best decision is no decision.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl bg-brand-night/5 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-bold text-text-primary">{pick.title}</h3>
            {pick.description && (
              <p className="mt-1 text-sm text-text-secondary">{pick.description}</p>
            )}
          </div>
          <span className="shrink-0 rounded-full bg-brand-cream/10 px-3 py-1 text-xs font-bold text-text-secondary">
            DO NOT ACT
          </span>
        </div>
        <p className="mt-3 text-sm leading-6 text-text-primary">{reason}</p>
        {Number(evidence.confirmed_inbound_qty) > 0 && (
          <p className="mt-2 text-xs text-text-secondary">
            Evidence: {Number(evidence.confirmed_inbound_qty)} confirmed inbound unit
            {Number(evidence.confirmed_inbound_qty) === 1 ? "" : "s"}
            {Boolean(evidence.ghost_po_risk) ? " · ⚠ ghost-PO risk detected" : ""}
          </p>
        )}
      </div>
    </section>
  );
}
