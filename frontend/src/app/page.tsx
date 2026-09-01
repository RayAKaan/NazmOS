'use client';

import { AuditProvider } from '@/components/landing/audit-context';
import { SiteHeader } from '@/components/landing/SiteHeader';
import { Hero } from '@/components/landing/Hero';
import { Problem } from '@/components/landing/Problem';
import {
  MemorySection,
  GraphSection,
  AgentsSection,
  ReasoningSection,
  DecisionSection,
  OutcomeSection,
} from '@/components/landing/StorySections';
import { FreeAudit } from '@/components/landing/FreeAudit';
import { HowItWorks } from '@/components/landing/HowItWorks';
import { BusinessMemory } from '@/components/landing/BusinessMemory';
import { Integrations } from '@/components/landing/Integrations';
import { RecoveryMatch } from '@/components/landing/RecoveryMatch';
import { Pricing } from '@/components/landing/Pricing';
import { FAQ } from '@/components/landing/FAQ';
import { FinalCTA } from '@/components/landing/FinalCTA';
import { SiteFooter } from '@/components/landing/SiteFooter';

export default function LandingPage() {
  return (
    <AuditProvider>
      <SiteHeader />
      <main id="main">
        <Hero />
        <Problem />
        <MemorySection />
        <GraphSection />
        <AgentsSection />
        <ReasoningSection />
        <DecisionSection />
        <OutcomeSection />
        <FreeAudit />
        <HowItWorks />
        <BusinessMemory />
        <Integrations />
        <RecoveryMatch />
        <Pricing />
        <FAQ />
        <FinalCTA />
      </main>
      <SiteFooter />
    </AuditProvider>
  );
}
