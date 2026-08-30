"use client";

import { useState } from "react";
import { RefreshCw, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { useActionCenter } from "@/hooks/useActionCenter";

/**
 * "Run Business Audit" — the primary CTA (Phase 2, brief §4). Triggers the
 * reusable audit engine across the domains that have reliable data, then
 * refreshes the Action Center.
 */
const DOMAINS = ["money_audit", "inventory", "recovery_match", "compliance"];

export function RunAuditButton() {
  const { businessId } = useAppStore();
  const { refresh } = useActionCenter();
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const run = async () => {
    if (!businessId || running) return;
    setRunning(true);
    setDone(null);
    try {
      for (const domain of DOMAINS) {
        try {
          await api.post("/audits/run", null, { params: { business_id: businessId, domain } });
        } catch {
          // a domain without data may fail; continue with the rest
        }
      }
      setDone("Audit complete");
      await refresh();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={run}
        disabled={running}
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
      >
        {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        {running ? "Auditing…" : "Run Business Audit"}
      </button>
      {done && <span className="text-xs text-success">{done}</span>}
    </div>
  );
}
