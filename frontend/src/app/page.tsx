"use client";

import { AuditProvider } from "@/components/landing/audit-context";
import { BusinessUniverse } from "@/components/universe";

/**
 * The public home — the Business Universe.
 *
 * A spatial, navigable model of the business system: SALES, INVENTORY, DEMAND,
 * SUPPLIERS, COST around central NAZMOS. Selecting a signal follows it through
 * the system; EXPLORE NAZMOS converges the field; REQUEST A BUSINESS AUDIT
 * embeds the live Money Audit (GuestAuditUploader). The `/` route is always
 * Convergence-dark (enforced reversibly inside BusinessUniverse).
 */
export default function NazmakHome() {
  return (
    <AuditProvider>
      <BusinessUniverse />
    </AuditProvider>
  );
}