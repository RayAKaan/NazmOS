'use client';

import { AuditProvider } from '@/components/landing/audit-context';
import { SiteHeader } from '@/components/landing/SiteHeader';
import { Hero } from '@/components/landing/Hero';
import { Problem } from '@/components/landing/Problem';
import { FreeAudit } from '@/components/landing/FreeAudit';
import { HowItWorks } from '@/components/landing/HowItWorks';
import { BusinessMemory } from '@/components/landing/BusinessMemory';
import { Integrations } from '@/components/landing/Integrations';
import { Trust } from '@/components/landing/Trust';
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
        <FreeAudit />
        <HowItWorks />
        <BusinessMemory />
        <Integrations />
        <Trust />
        <Pricing />
        <FAQ />
        <FinalCTA />
      </main>
      <SiteFooter />
    </AuditProvider>
  );
}
