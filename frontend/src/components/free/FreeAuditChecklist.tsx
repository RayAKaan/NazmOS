"use client";

import Link from "next/link";
import { CheckCircle2, FileSpreadsheet, LockKeyhole, MessageCircle, ShieldCheck, TrendingUp } from "lucide-react";

const steps = [
  [FileSpreadsheet, "Upload sales history", "Last 30–90 days from your POS or Excel."],
  [FileSpreadsheet, "Upload stock snapshot", "Current quantity, cost, shelf price, barcode if available."],
  [TrendingUp, "Review Money Audit", "Dead stock, stockout risk, margin leakage, trapped cash."],
  [MessageCircle, "Approve fixes", "Simple WhatsApp-style actions, not complicated software."],
] as const;

const fileColumns = [
  ["Sales file", "product name, sale date, quantity, price or total, cost if available"],
  ["Inventory file", "product name, current stock, cost, selling price, barcode, expiry if available"],
];

export function FreeAuditChecklist() {
  return (
    <div className="overflow-hidden rounded-3xl border border-white/10 bg-brand-night text-white shadow-2xl shadow-black/20">
      <div className="grid gap-0 lg:grid-cols-[1.15fr_.85fr]">
        <div className="p-6 md:p-7">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.24em] text-brand-amber">Free Money Audit</p>
              <h2 className="mt-3 text-2xl font-black md:text-3xl">Send two files. Find trapped cash.</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-white/62">
                NazmOS is built for busy merchants: no setup project, no long forms, no consultant language.
                Upload what your POS already exports and get a clear recovery plan.
              </p>
            </div>
            <div className="inline-flex shrink-0 items-center gap-2 rounded-full bg-emerald-400/10 px-3 py-2 text-xs font-bold text-emerald-300">
              <CheckCircle2 className="h-4 w-4" /> SAR 0 to start
            </div>
          </div>

          <div className="mt-6 grid gap-3 md:grid-cols-4">
            {steps.map(([Icon, title, body], i) => (
              <div key={title} className="rounded-2xl bg-white/[0.04] p-4 ring-1 ring-white/5">
                <Icon className="mb-3 h-5 w-5 text-brand-green" />
                <p className="font-bold">{i + 1}. {title}</p>
                <p className="mt-1 text-sm leading-5 text-white/55">{body}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <Link href="/upload" className="inline-flex justify-center rounded-xl bg-brand-amber px-5 py-3 font-bold text-black hover:bg-brand-gold">
              Start Free Audit
            </Link>
            <Link href="/product-demo" className="inline-flex justify-center rounded-xl border border-white/10 px-5 py-3 font-bold text-white/75 hover:bg-white/5 hover:text-white">
              See sample journey
            </Link>
          </div>
        </div>

        <div className="border-t border-white/10 bg-white/[0.03] p-6 md:p-7 lg:border-l lg:border-t-0">
          <div className="rounded-2xl border border-brand-amber/20 bg-brand-amber/10 p-4">
            <div className="flex items-center gap-2 text-brand-amber">
              <ShieldCheck className="h-5 w-5" />
              <p className="font-bold">What to prepare</p>
            </div>
            <div className="mt-4 space-y-3">
              {fileColumns.map(([title, body]) => (
                <div key={title} className="rounded-xl bg-black/20 p-3">
                  <p className="text-sm font-bold text-white">{title}</p>
                  <p className="mt-1 text-xs leading-5 text-white/55">{body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4">
            <div className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 h-5 w-5 text-brand-green" />
              <div>
                <p className="font-bold">User-first promise</p>
                <p className="mt-1 text-sm leading-6 text-white/55">
                  We only need retail operating data for the audit. If a column is confusing, skip it.
                  Founder-led pilots review the result before asking you to act.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
