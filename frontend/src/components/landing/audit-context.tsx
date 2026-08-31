"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { GuestAuditResult } from "@/components/landing/audit-types";

// Shared, client-side store for the most recent free-audit result. The GuestAuditUploader
// (in the #free-audit section) publishes here on success, and the Hero's live visual reads
// it so the "money at risk" panel stays in sync with a real, user-supplied audit result —
// rather than only ever showing static sample figures.
interface AuditContextValue {
  result: GuestAuditResult | null;
  setResult: (r: GuestAuditResult) => void;
}

const AuditContext = createContext<AuditContextValue | null>(null);

export function AuditProvider({ children }: { children: ReactNode }) {
  const [result, setResult] = useState<GuestAuditResult | null>(null);
  const set = useCallback((r: GuestAuditResult) => setResult(r), []);
  return <AuditContext.Provider value={{ result, setResult: set }}>{children}</AuditContext.Provider>;
}

export function useAudit() {
  const ctx = useContext(AuditContext);
  if (!ctx) throw new Error("useAudit must be used within AuditProvider");
  return ctx;
}
