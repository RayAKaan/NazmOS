"use client";

import Link from "next/link";
import { ArrowRight, FileSpreadsheet, MessageCircle, SearchCheck, WalletCards } from "lucide-react";

const outcomes = [
  [WalletCards, "Money at Risk", "Cash stuck in slow stock, risky stockouts, and weak margin items."],
  [SearchCheck, "Top recovery actions", "The exact products to discount, reorder, transfer, or watch."],
  [MessageCircle, "Approval-ready", "Actions written in plain merchant language for WhatsApp approval."],
] as const;

export function MoneyAuditEmptyState() {
  return (
    <section className="overflow-hidden rounded-3xl border border-brand-cream/10 bg-brand-night text-brand-cream shadow-2xl shadow-brand-night/20">
      <div className="grid gap-0 lg:grid-cols-[1fr_.9fr]">
        <div className="p-7 md:p-8">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">First user job</p>
          <h2 className="mt-3 max-w-2xl text-3xl font-black leading-tight md:text-5xl">
            No data yet. Start with the Free Money Audit.
          </h2>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-brand-cream/62">
            NazmOS becomes useful after it sees your sales and stock files. The first screen should not make
            you learn software — it should help you find recoverable cash.
          </p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <Link href="/upload" className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-amber px-5 py-3 font-bold text-brand-night hover:bg-brand-gold">
              Upload files <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/product-demo" className="inline-flex items-center justify-center gap-2 rounded-xl border border-brand-cream/10 px-5 py-3 font-bold text-brand-cream/75 hover:bg-brand-cream/5 hover:text-brand-cream">
              View sample audit
            </Link>
          </div>
        </div>

        <div className="border-t border-brand-cream/10 bg-brand-cream/[0.03] p-7 md:p-8 lg:border-l lg:border-t-0">
          <div className="rounded-2xl border border-brand-amber/20 bg-brand-amber/10 p-4">
            <div className="flex items-center gap-2 text-brand-amber">
              <FileSpreadsheet className="h-5 w-5" />
              <p className="font-bold">Minimum files</p>
            </div>
            <div className="mt-4 grid gap-3">
              <div className="rounded-xl bg-brand-night/20 p-3">
                <p className="text-sm font-bold">Sales history</p>
                <p className="mt-1 text-xs leading-5 text-brand-cream/55">Product, date, quantity, price/total. 30–90 days is enough.</p>
              </div>
              <div className="rounded-xl bg-brand-night/20 p-3">
                <p className="text-sm font-bold">Inventory snapshot</p>
                <p className="mt-1 text-xs leading-5 text-brand-cream/55">Product, current stock, cost, selling price. Barcode helps matching.</p>
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-3">
            {outcomes.map(([Icon, title, body]) => (
              <div key={title} className="flex gap-3 rounded-2xl bg-brand-night/20 p-4 ring-1 ring-brand-cream/5">
                <Icon className="mt-0.5 h-5 w-5 text-brand-green" />
                <div>
                  <p className="font-bold">{title}</p>
                  <p className="mt-1 text-sm leading-6 text-brand-cream/55">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
