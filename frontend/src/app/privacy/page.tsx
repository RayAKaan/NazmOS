import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "NazmOS privacy policy and data handling practices for merchants using the inventory intelligence platform.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-brand-night px-5 py-12 text-brand-cream md:px-8">
      <div className="mx-auto max-w-3xl rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-10">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">Nazmak privacy baseline</p>
        <h1 className="mt-4 font-serif text-4xl font-black tracking-[-0.04em] md:text-6xl">Privacy Policy</h1>
        <p className="mt-4 text-sm leading-7 text-white/62">
          This pilot privacy policy is written for the NazmOS Retail Recovery System. It is not a replacement for formal legal review before scale.
        </p>

        <div className="mt-8 space-y-6 text-sm leading-7 text-white/68">
          <section>
            <h2 className="text-xl font-bold text-white">1. Data we collect</h2>
            <p className="mt-2">NazmOS collects account details, business details, uploaded sales files, inventory files, product data, stock quantities, costs, prices, approval actions, and Recovery Match activity.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-white">2. Why we use it</h2>
            <p className="mt-2">We use merchant data to generate Money Audits, detect dead stock, estimate stockout risk, identify margin leakage, create approval-ready recovery actions, and operate controlled Recovery Match pilots.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-white">3. File handling</h2>
            <p className="mt-2">Uploaded files are used for import and audit generation. Production deployments should configure retention limits, encrypted storage, access logging, and deletion on merchant request.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-white">4. Recovery Match</h2>
            <p className="mt-2">Contact details are not automatically revealed. In v1, both parties must approve and risky categories are excluded. NazmOS does not handle payment, escrow, or delivery.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-white">5. Access</h2>
            <p className="mt-2">Founder/support access should be limited to pilot operation, file troubleshooting, audit review, and support. Production access should be logged and role-controlled.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-white">6. Contact</h2>
            <p className="mt-2">For pilot data requests, contact Nazmak support/founder directly. Replace this section with the official company contact before public launch.</p>
          </section>
        </div>

        <Link href="/" className="mt-8 inline-flex rounded-xl bg-brand-amber px-5 py-3 font-bold text-black hover:bg-brand-gold">Back to NazmOS</Link>
      </div>
    </main>
  );
}
