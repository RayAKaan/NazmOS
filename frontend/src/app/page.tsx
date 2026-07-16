'use client';

import Link from 'next/link';
import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  FileSpreadsheet,
  MessageCircle,
  MoveRight,
  ShieldCheck,
  Store,
  TrendingUp,
  WalletCards,
} from 'lucide-react';

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
};

const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const moneyRows = [
  ['Money at Risk', 'SAR 143,000', 'Potential annual leakage found in 48 hours', 'text-[#C8412A]'],
  ['Money Approved', 'SAR 41,000', 'Owner-approved recovery actions', 'text-[#E0B34A]'],
  ['Money Recovered', 'SAR 27,000', 'Protected or recovered after action', 'text-[#13A05A]'],
];

const watchCards = [
  ['Cash Leakage', 'Dead stock, overstock, and slow-moving inventory trapping cash.', WalletCards, '#C8412A'],
  ['Stockout Risk', 'Fast-moving items likely to finish before weekend or Ramadan demand.', Store, '#E0B34A'],
  ['Margin Drops', 'Supplier costs increasing quietly reducing your profit.', TrendingUp, '#13A05A'],
  ['Branch Imbalance', 'One branch overstocked while another is about to run out.', Activity, '#F4EFE6'],
];

const pricingCards = [
  ['Free Money Audit', 'SAR 0', 'Send two files. Get a Money Audit in 48 hours.', ['2 uploads/month', '1 audit/month', 'Mock WhatsApp', 'Recovery Match preview']],
  ['30-Day Recovery Pilot', 'SAR 3,000', 'Credited toward annual license if you continue.', ['Weekly reports', 'WhatsApp actions', 'Founder support', 'SAR 9,000 identification guarantee']],
  ['Annual Plans', 'From SAR 6,900/year', 'Small Retail, Growing Retail, and custom chain plans.', ['Small Retail', 'Growing Retail', 'Large Chains custom', 'Partner add-ons when needed']],
];

const demoTabs = [
  { id: 'audit', label: 'Money Audit' },
  { id: 'whatsapp', label: 'WhatsApp COO' },
  { id: 'report', label: 'Weekly Report' },
] as const;

type DemoTab = typeof demoTabs[number]['id'];

function NazmakMark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 96 96" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="nazmakGold" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#F1DEC2" />
          <stop offset="55%" stopColor="#CBB38A" />
          <stop offset="100%" stopColor="#8B6A39" />
        </linearGradient>
      </defs>
      <path
        d="M19 62 C33 62 39 50 48 41 C56 32 64 29 77 35"
        fill="none"
        stroke="url(#nazmakGold)"
        strokeWidth="14"
        strokeLinecap="round"
      />
      <path
        d="M33 64 C44 64 52 60 58 51"
        fill="none"
        stroke="url(#nazmakGold)"
        strokeWidth="10"
        strokeLinecap="round"
        opacity="0.92"
      />
      <rect x="44" y="13" width="14" height="14" rx="2" fill="url(#nazmakGold)" transform="rotate(45 51 20)" />
    </svg>
  );
}

function SectionLabel({ children, dark = false }: { children: React.ReactNode; dark?: boolean }) {
  return (
    <div className={`inline-flex items-center gap-3 font-mono text-[11px] font-bold uppercase tracking-[0.28em] ${dark ? 'text-[#E0B34A]' : 'text-[#0B6B3A]'}`}>
      <span className={`h-px w-8 ${dark ? 'bg-[#E0B34A]/60' : 'bg-[#0B6B3A]/60'}`} />
      {children}
    </div>
  );
}

function DemoPanel({ active }: { active: DemoTab }) {
  if (active === 'whatsapp') {
    return (
      <div className="mx-auto w-full max-w-sm rounded-[2rem] border border-white/10 bg-black p-4 shadow-2xl shadow-black/40">
        <div className="rounded-[1.5rem] bg-[#0B141A] p-4">
          <div className="mb-4 flex items-center gap-3 border-b border-white/10 pb-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#0B6B3A] font-bold">N</div>
            <div>
              <p className="font-bold text-white">NazmOS</p>
              <p className="text-xs text-white/45">by Nazmak · business account</p>
            </div>
          </div>
          <div className="space-y-3">
            <div className="rounded-2xl bg-[#3D2820] p-4 text-sm leading-6 text-white">
              <b className="text-[#ff8a73]">Stockout warning</b>
              <br />Almarai Milk may finish in 1.8 days.
            </div>
            <div className="rounded-2xl bg-[#1F2C33] p-4 text-sm leading-6 text-white">
              Recommended reorder:
              <br />
              <b className="text-[#E0B34A]">120 units · SAR 840</b>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button className="rounded-xl bg-[#25D366] py-3 font-bold text-black">✓ Approve</button>
              <button className="rounded-xl bg-white/10 py-3 font-bold text-white">Reject</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (active === 'report') {
    return (
      <div className="rounded-[2rem] border border-white/10 bg-[#F4EFE6] p-5 text-[#0A0E0C] shadow-2xl">
        <div className="mb-5 flex items-start justify-between border-b border-black/10 pb-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[.22em] text-[#0B6B3A]">Thursday Money Report</p>
            <h3 className="mt-1 font-serif text-3xl font-black">Store Health: 82/100</h3>
          </div>
          <span className="rounded-full bg-[#0B6B3A]/10 px-3 py-1 text-xs font-bold text-[#0B6B3A]">Sample</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {moneyRows.map(([label, value, desc, color]) => (
            <div key={label} className="rounded-2xl border border-black/10 bg-white/60 p-4">
              <p className="font-mono text-[10px] uppercase tracking-[.2em] text-black/40">{label}</p>
              <p className={`mt-2 font-serif text-2xl font-black ${color}`}>{value}</p>
              <p className="mt-2 text-xs leading-5 text-black/55">{desc}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-2xl bg-[#0A0E0C] p-4 text-[#F4EFE6]">
          <p className="font-mono text-[10px] uppercase tracking-[.2em] text-[#E0B34A]">Top action</p>
          <p className="mt-2 font-serif text-xl font-black">Transfer milk from Branch 2 before Friday.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-[2rem] border border-white/10 bg-[#F4EFE6] p-5 text-[#0A0E0C] shadow-2xl">
      <div className="rounded-[1.5rem] bg-[#0A0E0C] p-5 text-[#F4EFE6]">
        <div className="mb-5 flex items-center justify-between border-b border-white/10 pb-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[.22em] text-[#E0B34A]">Sample Money Audit</p>
            <h3 className="mt-1 font-serif text-2xl font-black">Abu Fahad Markets</h3>
          </div>
          <span className="rounded-full bg-[#C8412A]/15 px-3 py-1 text-xs font-bold text-[#ff8a73]">48h report</span>
        </div>
        <div className="space-y-3">
          {moneyRows.map(([label, value, desc, color]) => (
            <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <p className="font-mono text-[10px] uppercase tracking-[.22em] text-white/45">{label}</p>
              <p className={`mt-1 font-serif text-3xl font-black ${color}`}>{value}</p>
              <p className="mt-1 text-sm text-white/55">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const [activeDemo, setActiveDemo] = useState<DemoTab>('audit');

  return (
    <main className="min-h-screen bg-[#0A0E0C] text-[#F4EFE6] selection:bg-[#E0B34A] selection:text-[#0A0E0C]">
      <nav className="sticky top-0 z-40 border-b border-white/10 bg-[#0A0E0C]/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 md:px-8">
          <Link href="/" className="flex items-center gap-3">
            <NazmakMark className="h-9 w-9" />
            <div>
              <span className="block font-serif text-xl font-black tracking-tight">nazmak</span>
              <span className="block font-mono text-[9px] uppercase tracking-[0.28em] text-[#CBB38A]">creators of NazmOS</span>
            </div>
          </Link>
          <div className="hidden items-center gap-8 text-sm text-[#F4EFE6]/65 md:flex">
            <a href="#product" className="hover:text-white">NazmOS</a>
            <a href="#demo" className="hover:text-white">Demo</a>
            <a href="#pricing" className="hover:text-white">Pricing</a>
          </div>
          <Link href="/product-demo" className="rounded-full border border-[#E0B34A]/50 px-4 py-2 text-sm font-semibold text-[#E0B34A] hover:bg-[#E0B34A] hover:text-[#0A0E0C]">
            Run interactive demo
          </Link>
        </div>
      </nav>

      <section className="relative overflow-hidden px-5 py-20 md:px-8 md:py-28">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_75%_18%,rgba(203,179,138,.22),transparent_34%),radial-gradient(circle_at_20%_82%,rgba(19,160,90,.16),transparent_34%)]" />
        <div className="absolute inset-0 opacity-[0.03] [background-image:linear-gradient(#fff_1px,transparent_1px),linear-gradient(90deg,#fff_1px,transparent_1px)] [background-size:72px_72px]" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[1.05fr_.95fr]">
          <motion.div variants={stagger} initial="hidden" animate="visible" className="space-y-8">
            <motion.div variants={fadeUp} className="inline-flex items-center gap-3 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs font-bold uppercase tracking-[0.24em] text-[#E0B34A]">
              <NazmakMark className="h-5 w-5" /> Bring order to business
            </motion.div>
            <motion.div variants={fadeUp}>
              <p className="mb-4 font-mono text-xs uppercase tracking-[0.28em] text-[#CBB38A]">Nazmak presents NazmOS</p>
              <h1 className="max-w-4xl font-serif text-5xl font-black leading-[0.95] tracking-[-0.04em] md:text-7xl lg:text-8xl">
                Find the cash trapped inside your store.
              </h1>
            </motion.div>
            <motion.p variants={fadeUp} className="max-w-2xl text-lg leading-8 text-[#F4EFE6]/72 md:text-xl">
              Nazmak builds NazmOS — the Retail Recovery System that audits your sales and inventory, finds dead stock, prevents stockouts, protects margins, and sends owner approvals on WhatsApp.
            </motion.p>
            <motion.div variants={fadeUp} className="flex flex-col gap-3 sm:flex-row">
              <Link href="/register?intent=free-audit" className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#E0B34A] px-6 py-4 font-bold text-[#0A0E0C] shadow-2xl shadow-[#E0B34A]/20 hover:bg-[#f0c765]">
                Get a Free Money Audit <ArrowRight className="h-4 w-4" />
              </Link>
              <a href="#demo" className="inline-flex items-center justify-center rounded-2xl border border-white/12 px-6 py-4 font-semibold text-white/80 hover:bg-white/5">
                Watch the demo
              </a>
            </motion.div>
            <motion.p variants={fadeUp} className="text-sm text-[#F4EFE6]/50">
              No POS replacement. No customer names needed. Excel, CSV, or POS export is fine.
            </motion.p>
          </motion.div>

          <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7 }}>
            <DemoPanel active="audit" />
          </motion.div>
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#F4EFE6] px-5 py-12 text-[#0A0E0C] md:px-8">
        <div className="mx-auto grid max-w-7xl gap-4 md:grid-cols-3">
          {[
            [FileSpreadsheet, 'Send two files', 'Sales export + inventory export. No customer names needed.'],
            [TrendingUp, 'Get a Money Audit', 'Dead stock, stockout risk, margin leakage, and value estimate.'],
            [MessageCircle, 'Approve fixes', 'Owner actions delivered through WhatsApp, not daily dashboards.'],
          ].map(([Icon, title, body]) => {
            const LucideIcon = Icon as typeof FileSpreadsheet;
            return (
              <div key={title as string} className="rounded-3xl border border-black/10 bg-[#ECE5D6] p-6">
                <LucideIcon className="mb-4 h-6 w-6 text-[#0B6B3A]" />
                <h3 className="font-serif text-2xl font-black">{title as string}</h3>
                <p className="mt-3 leading-7 text-black/62">{body as string}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section id="product" className="px-5 py-20 md:px-8">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
          <div>
            <SectionLabel dark>Nazmak → NazmOS</SectionLabel>
            <h2 className="mt-4 font-serif text-4xl font-black leading-tight tracking-[-.03em] md:text-6xl">A company for business order. A product for retail recovery.</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
              <NazmakMark className="mb-5 h-12 w-12" />
              <p className="font-mono text-xs uppercase tracking-[.22em] text-[#E0B34A]">Company</p>
              <h3 className="mt-3 font-serif text-3xl font-black">Nazmak</h3>
              <p className="mt-3 leading-7 text-white/58">Builds recovery systems that bring order to Saudi business operations.</p>
            </div>
            <div className="rounded-3xl border border-[#E0B34A]/25 bg-[#E0B34A]/10 p-6">
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#E0B34A] font-serif text-xl font-black text-[#0A0E0C]">N</div>
              <p className="font-mono text-xs uppercase tracking-[.22em] text-[#E0B34A]">Product</p>
              <h3 className="mt-3 font-serif text-3xl font-black">NazmOS</h3>
              <p className="mt-3 leading-7 text-white/58">The Retail Recovery System that finds cash leakage and sends owner actions.</p>
            </div>
          </div>
        </div>
      </section>

      <section id="audit" className="bg-[#F4EFE6] px-5 py-20 text-[#0A0E0C] md:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="mb-12 max-w-3xl">
            <SectionLabel>What NazmOS watches</SectionLabel>
            <h2 className="mt-4 font-serif text-4xl font-black tracking-[-.03em] md:text-6xl">Four ways stores lose money quietly.</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {watchCards.map(([title, body, Icon, color], i) => {
              const LucideIcon = Icon as typeof WalletCards;
              return (
                <div key={title as string} className="rounded-3xl border border-black/10 bg-[#ECE5D6] p-6">
                  <div className="mb-10 flex items-center justify-between">
                    <span className="font-mono text-xs text-black/40">0{i + 1}</span>
                    <LucideIcon className="h-5 w-5" style={{ color: color as string }} />
                  </div>
                  <h3 className="font-serif text-2xl font-black">{title as string}</h3>
                  <p className="mt-4 leading-7 text-black/62">{body as string}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section id="demo" className="px-5 py-20 md:px-8">
        <div className="mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <SectionLabel dark>Product demo</SectionLabel>
            <h2 className="mt-4 font-serif text-4xl font-black leading-tight tracking-[-.03em] md:text-6xl">The dashboard is not the product. The weekly recovery habit is.</h2>
            <p className="mt-6 max-w-xl text-lg leading-8 text-white/62">Use the tabs to see the three moments that matter: audit, approval, and weekly proof.</p>
            <div className="mt-8 flex flex-wrap gap-2">
              {demoTabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveDemo(tab.id)}
                  className={`rounded-full px-4 py-2 text-sm font-bold transition ${activeDemo === tab.id ? 'bg-[#E0B34A] text-[#0A0E0C]' : 'border border-white/10 text-white/62 hover:bg-white/5 hover:text-white'}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
          <DemoPanel active={activeDemo} />
        </div>
      </section>

      <section id="pricing" className="bg-[#F4EFE6] px-5 py-20 text-[#0A0E0C] md:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="mb-10 max-w-3xl">
            <SectionLabel>Start small, prove value</SectionLabel>
            <h2 className="mt-4 font-serif text-4xl font-black md:text-6xl">Simple pricing after we prove value.</h2>
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            {pricingCards.map(([title, price, body, features]) => (
              <div key={title as string} className="rounded-3xl border border-black/10 bg-[#ECE5D6] p-7">
                <h3 className="font-serif text-2xl font-black">{title as string}</h3>
                <p className="mt-4 font-serif text-3xl font-black text-[#0B6B3A]">{price as string}</p>
                <p className="mt-4 leading-7 text-black/62">{body as string}</p>
                <ul className="mt-6 space-y-2">
                  {(features as string[]).map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm text-black/65">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#0B6B3A]" /> {feature}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-5 py-16 md:px-8">
        <div className="mx-auto max-w-7xl rounded-[2rem] border border-white/10 bg-white/[0.03] p-8 md:p-10">
          <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-emerald-400/10 px-3 py-2 text-xs font-bold text-emerald-300">
                <ShieldCheck className="h-4 w-4" /> Free tier honesty
              </div>
              <h2 className="font-serif text-3xl font-black md:text-5xl">Free proves value. Paid plans unlock continuous recovery.</h2>
              <p className="mt-4 max-w-3xl leading-7 text-white/60">Free shows your Money Audit. Paid plans unlock weekly recovery reports, live approvals, and Recovery Match between nearby stores.</p>
            </div>
            <Link href="/register?intent=free-audit" className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#E0B34A] px-6 py-4 font-bold text-[#0A0E0C] hover:bg-[#f0c765]">
              Get a Free Money Audit <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="px-5 py-12 md:px-8">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 border-t border-white/10 pt-8 md:flex-row md:items-center">
          <div className="flex items-center gap-3">
            <NazmakMark className="h-10 w-10" />
            <div>
              <p className="font-serif text-2xl font-black">nazmak</p>
              <p className="mt-1 text-sm text-white/50">Company behind NazmOS Retail Recovery.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Link href="/privacy" className="text-sm font-semibold text-white/45 hover:text-white">Privacy</Link>
            <Link href="/terms" className="text-sm font-semibold text-white/45 hover:text-white">Terms</Link>
            <Link href="/register?intent=free-audit" className="inline-flex items-center gap-2 rounded-2xl bg-[#E0B34A] px-5 py-3 font-bold text-[#0A0E0C]">
              Get a Free Money Audit <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
