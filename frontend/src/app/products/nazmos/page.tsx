"use client";

import { AuditProvider } from "@/components/landing/audit-context";
import { NazmakNav } from "@/components/nazmak/NazmakNav";
import { NazmakFooter } from "@/components/nazmak/NazmakFooter";
import {
  NazmosHero,
  DataStory,
  BusinessMemoryStory,
  KnowledgeGraphStory,
  AgentSystem,
  ReasoningGate,
  DecisionStory,
  OutcomeLoop,
  FreeAuditExperience,
  NazmosCTA,
} from "@/components/nazmos";
import { SectionTransition } from "@/components/motion/SectionTransition";

/**
 * /products/nazmos — the NazmOS product page.
 *
 * Narrative arc:
 *   Hero (fragmented data → system → context → decision)
 *   Data        — what comes in
 *   Memory      — accumulated business context
 *   Graph       — how things relate
 *   Agents      — specialists over the shared context
 *   Reasoning   — deterministic + bounded AI
 *   Decision    — a concrete sample decision moment
 *   Outcomes    — the compounding loop (clearly labelled sample)
 *   Free Audit  — live conversion
 *   CTA         — back to company / into the audit
 *
 * Uses the same Nav/Footer as the company page so the two-tier brand stays
 * coherent: Nazmak is the parent, NazmOS is the product.
 */
export default function NazmosProductPage() {
  return (
    <AuditProvider>
      <NazmakNav />
      <main id="main">
        <NazmosHero />
        <DataStory />
        <BusinessMemoryStory />
        <KnowledgeGraphStory />
        <AgentSystem />
        <ReasoningGate />
        <DecisionStory />
        <OutcomeLoop />
        <FreeAuditExperience />
        <NazmosCTA />
      </main>
      <NazmakFooter />
    </AuditProvider>
  );
}
