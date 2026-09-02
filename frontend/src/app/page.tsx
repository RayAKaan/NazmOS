"use client";

import { AuditProvider } from "@/components/landing/audit-context";
import {
  NazmakNav,
  NazmakHero,
  NazmakBuilding,
  CurrentCapabilities,
  NazmosIntro,
  NazmosHowItWorks,
  FutureScaleVisual,
  NazmakPrinciples,
  NazmakStatement,
  NazmakFreeAudit,
  NazmakFooter,
} from "@/components/nazmak";
import { SectionTransition } from "@/components/motion/SectionTransition";

/**
 * Nazmak — the company homepage.
 *
 * Establishes the parent brand, then introduces NazmOS as its first product.
 * The sequence: who Nazmak is → what it builds → current capability →
 * NazmOS → how it works → future scale → principles → final statement.
 */
export default function NazmakHome() {
  return (
    <AuditProvider>
      <NazmakNav />
      <main id="main">
        <NazmakHero />

        <SectionTransition className="mx-auto max-w-7xl px-5 md:px-8" />
        <NazmakBuilding />

        <SectionTransition className="mx-auto max-w-7xl px-5 md:px-8" />
        <CurrentCapabilities />

        <NazmosIntro />

        <SectionTransition className="mx-auto max-w-7xl px-5 md:px-8" />
        <NazmosHowItWorks />

        <FutureScaleVisual />

        <NazmakPrinciples />

        <NazmakFreeAudit />

        <NazmakStatement />
      </main>
      <NazmakFooter />
    </AuditProvider>
  );
}
