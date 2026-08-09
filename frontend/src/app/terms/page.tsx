import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Use",
  description: "NazmOS terms of use, product scope, merchant responsibilities, and Recovery Match limitations.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-brand-night px-5 py-12 text-brand-cream md:px-8">
      <div className="mx-auto max-w-3xl rounded-3xl border border-brand-cream/10 bg-brand-cream/[0.03] p-6 md:p-10">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">Nazmak pilot terms</p>
        <h1 className="mt-4 font-serif text-4xl font-black tracking-[-0.04em] md:text-6xl">Terms of Use</h1>
        <p className="mt-4 text-sm leading-7 text-brand-cream/62">
          These are practical pilot terms for NazmOS. Get formal Saudi legal review before scaling beyond controlled pilots.
        </p>

        <div className="mt-8 space-y-6 text-sm leading-7 text-brand-cream/68">
          <section>
            <h2 className="text-xl font-bold text-brand-cream">1. Product scope</h2>
            <p className="mt-2">NazmOS is a Retail Recovery System. It helps merchants detect trapped cash through Money Audits, stockout risk, margin leakage, approval actions, weekly reports, and controlled Recovery Match workflows.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-brand-cream">2. Audit estimates</h2>
            <p className="mt-2">Money at Risk, Money Approved, and Money Recovered are operational estimates based on uploaded data quality. They are not financial, accounting, tax, or legal guarantees.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-brand-cream">3. Merchant responsibility</h2>
            <p className="mt-2">Merchants remain responsible for validating quantities, prices, expiry dates, product condition, supplier agreements, and any action taken based on NazmOS recommendations.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-brand-cream">4. Recovery Match limitations</h2>
            <p className="mt-2">Recovery Match v1 is manual-confirm. NazmOS does not provide escrow, payment processing, delivery, inspection, invoice generation, or regulated-category clearance.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-brand-cream">5. Excluded categories</h2>
            <p className="mt-2">Near-expiry stock, expired stock, cold-chain products, medicine, baby formula, fresh dairy, frozen goods, meat, cosmetics, and regulated categories are excluded from Recovery Match v1.</p>
          </section>
          <section>
            <h2 className="text-xl font-bold text-brand-cream">6. Pilot support</h2>
            <p className="mt-2">Founder-led pilots may include manual file review, manual WhatsApp messaging, and manual action logging. This is intentional until enough real merchant workflows are observed.</p>
          </section>
        </div>

        <Link href="/" className="mt-8 inline-flex rounded-xl bg-brand-amber px-5 py-3 font-bold text-brand-night hover:bg-brand-gold">Back to NazmOS</Link>
      </div>
    </main>
  );
}
