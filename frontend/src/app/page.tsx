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
import { GuestAuditUploader } from '@/components/landing/GuestAuditUploader';
import { SplitText } from '@/components/ui/SplitText';
import { AmbientBackground } from '@/components/ui/AmbientBackground';
import { ShineBorder } from '@/components/ui/ShineBorder';
import { Marquee } from '@/components/ui/Marquee';

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] } },
};

const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const moneyRows = [
  ['Money at Risk', 'SAR 143,000', 'Potential annual leakage found in 48 hours', 'text-brand-red'],
  ['Money Approved', 'SAR 41,000', 'Owner-approved recovery actions', 'text-brand-amber'],
  ['Money Recovered', 'SAR 27,000', 'Protected or recovered after action', 'text-brand-green'],
];

const watchCards = [
  ['Cash Leakage', 'Dead stock, overstock, and slow-moving inventory trapping cash.', WalletCards, 'var(--brand-red)'],
  ['Stockout Risk', 'Fast-moving items likely to finish before weekend or Ramadan demand.', Store, 'var(--brand-amber)'],
  ['Margin Drops', 'Supplier costs increasing quietly reducing your profit.', TrendingUp, 'var(--brand-green)'],
  ['Branch Imbalance', 'One branch overstocked while another is about to run out.', Activity, 'var(--brand-cream)'],
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
          <stop offset="0%" stopColor="var(--brand-gold)" />
          <stop offset="55%" stopColor="var(--brand-gold-soft)" />
          <stop offset="100%" stopColor="var(--brand-sand)" />
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
    <div className={`inline-flex items-center gap-3 font-mono text-[11px] font-bold uppercase tracking-[0.28em] ${dark ? 'text-brand-amber' : 'text-whatsapp-deep'}`}>
      <span className={`h-px w-8 ${dark ? 'bg-brand-amber/60' : 'bg-whatsapp-deep/60'}`} />
      {children}
    </div>
  );
}

function DemoPanel({ active }: { active: DemoTab }) {
  if (active === 'whatsapp') {
    return (
      <div className="mx-auto w-full max-w-sm rounded-[2rem] border border-brand-cream/10 bg-brand-night p-4 shadow-2xl shadow-brand-night/40">
        <div className="rounded-[1.5rem] bg-chat-deep p-4">
          <div className="mb-4 flex items-center gap-3 border-b border-brand-cream/10 pb-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-whatsapp-deep font-bold">N</div>
            <div>
              <p className="font-bold text-brand-cream">NazmOS</p>
              <p className="text-xs text-brand-cream/45">by Nazmak · business account</p>
            </div>
          </div>
          <div className="space-y-3">
            <div className="rounded-2xl bg-chat-warm p-4 text-sm leading-6 text-brand-cream">
              <b className="text-brand-red-light">Stockout warning</b>
              <br />Almarai Milk may finish in 1.8 days.
            </div>
            <div className="rounded-2xl bg-chat-steel p-4 text-sm leading-6 text-brand-cream">
              Recommended reorder:
              <br />
              <b className="text-brand-amber">120 units · SAR 840</b>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button className="rounded-xl bg-whatsapp py-3 font-bold text-brand-night">✓ Approve</button>
                <button className="rounded-xl bg-brand-cream/10 py-3 font-bold text-brand-cream">Reject</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (active === 'report') {
    return (
      <div className="rounded-[2rem] border border-brand-night/10 bg-brand-cream p-5 text-brand-night shadow-2xl">
        <div className="mb-5 flex items-start justify-between border-b border-brand-night/10 pb-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[.22em] text-whatsapp-deep">Thursday Money Report</p>
            <h3 className="mt-1 font-serif text-3xl font-black">Store Health: 82/100</h3>
          </div>
          <span className="rounded-full bg-whatsapp-deep/10 px-3 py-1 text-xs font-bold text-whatsapp-deep">Sample</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {moneyRows.map(([label, value, desc, color]) => (
            <div key={label} className="rounded-2xl border border-brand-night/10 bg-brand-cream/60 p-4">
              <p className="font-mono text-[10px] uppercase tracking-[.2em] text-brand-night/40">{label}</p>
              <p className={`mt-2 font-serif text-2xl font-black ${color}`}>{value}</p>
              <p className="mt-2 text-xs leading-5 text-brand-night/55">{desc}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-2xl bg-brand-night p-4 text-brand-cream">
          <p className="font-mono text-[10px] uppercase tracking-[.2em] text-brand-amber">Top action</p>
          <p className="mt-2 font-serif text-xl font-black">Transfer milk from Branch 2 before Friday.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-[2rem] border border-brand-night/10 bg-brand-cream p-5 text-brand-night shadow-2xl">
      <div className="rounded-[1.5rem] bg-brand-night p-5 text-brand-cream">
        <div className="mb-5 flex items-center justify-between border-b border-brand-cream/10 pb-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[.22em] text-brand-amber">Sample Money Audit</p>
            <h3 className="mt-1 font-serif text-2xl font-black">Abu Fahad Markets</h3>
          </div>
          <span className="rounded-full bg-brand-red/15 px-3 py-1 text-xs font-bold text-brand-cream">48h report</span>
        </div>
        <div className="space-y-3">
          {moneyRows.map(([label, value, desc, color]) => (
            <div key={label} className="rounded-2xl border border-brand-cream/10 bg-brand-cream/[0.04] p-4">
              <p className="font-mono text-[10px] uppercase tracking-[.22em] text-brand-cream/45">{label}</p>
              <p className={`mt-1 font-serif text-3xl font-black ${color}`}>{value}</p>
              <p className="mt-1 text-sm text-brand-cream/55">{desc}</p>
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
    <main className="min-h-screen bg-brand-night text-brand-cream selection:bg-brand-amber selection:text-brand-night">
      <nav className="sticky top-0 z-40 border-b border-brand-cream/10 bg-brand-night/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 md:px-8">
          <Link href="/" className="flex items-center gap-3">
            <NazmakMark className="h-9 w-9" />
            <div>
              <span className="block font-serif text-xl font-black tracking-tight">nazmak</span>
              <span className="block font-mono text-[9px] uppercase tracking-[0.28em] text-brand-sand">creators of NazmOS</span>
            </div>
          </Link>
          <div className="hidden items-center gap-8 text-sm text-brand-cream/65 md:flex">
            <a href="#product" className="hover:text-brand-cream">NazmOS</a>
            <a href="#demo" className="hover:text-brand-cream">Demo</a>
            <a href="#pricing" className="hover:text-brand-cream">Pricing</a>
          </div>
          <Link href="/product-demo" className="rounded-full border border-brand-amber/50 px-4 py-2 text-sm font-semibold text-brand-amber hover:bg-brand-amber hover:text-brand-night">
            Run interactive demo
          </Link>
        </div>
      </nav>

      <section className="relative overflow-hidden px-5 py-20 md:px-8 md:py-28">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_75%_18%,color-mix(in_oklab,var(--brand-gold)_22%,transparent),transparent_34%),radial-gradient(circle_at_20%_82%,color-mix(in_oklab,var(--brand-green)_16%,transparent),transparent_34%)]" />
        {/* §C: slow low-opacity gold/teal aurora behind the hero — brand-forward only */}
        <AmbientBackground />
        <div className="absolute inset-0 opacity-[0.03] [background-image:linear-gradient(var(--brand-cream)_1px,transparent_1px),linear-gradient(90deg,var(--brand-cream)_1px,transparent_1px)] [background-size:72px_72px]" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[1.05fr_.95fr]">
          <motion.div variants={stagger} initial="hidden" animate="visible" className="space-y-8">
            <motion.div variants={fadeUp} className="inline-flex items-center gap-3 rounded-full border border-brand-cream/10 bg-brand-cream/5 px-4 py-2 text-xs font-bold uppercase tracking-[0.24em] text-brand-amber">
              <NazmakMark className="h-5 w-5" /> Bring order to business
            </motion.div>
            <motion.div variants={fadeUp}>
              <p className="mb-4 font-mono text-xs uppercase tracking-[0.28em] text-brand-sand">Nazmak presents NazmOS</p>
              <h1 className="max-w-4xl font-serif text-5xl font-black leading-[0.95] tracking-[-0.04em] md:text-7xl lg:text-8xl">
                <SplitText text="Find the cash trapped inside your store." delay={0.2} />
              </h1>
            </motion.div>
            <motion.p variants={fadeUp} className="max-w-2xl text-lg leading-8 text-brand-cream/72 md:text-xl">
              Nazmak builds NazmOS — the Retail Recovery System that audits your sales and inventory, finds dead stock, prevents stockouts, protects margins, and sends owner approvals on WhatsApp.
            </motion.p>
            <motion.div variants={fadeUp} className="flex flex-col gap-3 sm:flex-row">
              {/* §B: gold ShineBorder reserved for the PRIMARY CTA only */}
              <ShineBorder className="inline-flex rounded-2xl">
                <a href="#free-audit" className="inline-flex items-center justify-center gap-2 rounded-2xl bg-brand-amber px-6 py-4 font-bold text-brand-night shadow-2xl shadow-brand-amber/20 hover:bg-brand-gold-soft">
                  Upload Sales + Inventory — Analyze Free <ArrowRight className="h-4 w-4" />
                </a>
              </ShineBorder>
              <a href="#demo" className="inline-flex items-center justify-center rounded-2xl border border-brand-cream/12 px-6 py-4 font-semibold text-brand-cream/80 hover:bg-brand-cream/5">
                Watch the demo
              </a>
            </motion.div>
            <motion.p variants={fadeUp} className="text-sm text-brand-cream/50">
              Two files in, trapped cash out. No POS replacement, no customer names, no sign-up.
            </motion.p>
          </motion.div>

          <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7 }}>
            <DemoPanel active="audit" />
          </motion.div>
        </div>
      </section>

      {/* §D: partner/merchant logo strip — continuous marquee, immediate B2B premium signal */}
      <section aria-label="Trusted by stores across Saudi Arabia" className="border-b border-brand-cream/10 px-5 py-10 md:px-8">
        <div className="mx-auto max-w-7xl">
          <p className="mb-6 text-center font-mono text-xs uppercase tracking-[0.28em] text-brand-sand">
            Recovery systems at work across the Kingdom
          </p>
          <Marquee speed={30} gap={64}>
            {["Manara Markets", "Souq Al-Watan", "Al-Rawdah Mart", "Nakhla", "Wadi Stores", "Al-Faisal", "Joud Retail", "Sahari"].map((name) => (
              <span key={name} className="whitespace-nowrap font-serif text-2xl font-black text-brand-cream/35">
                {name}
              </span>
            ))}
          </Marquee>
        </div>
      </section>

      <section id="free-audit" className="border-y border-brand-cream/10 bg-brand-night px-5 py-16 md:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="mb-10 text-center">
            <SectionLabel dark>Try it free</SectionLabel>
            <h2 className="mt-4 font-serif text-4xl font-black tracking-[-.03em] md:text-5xl">
              See your trapped cash in under 60 seconds
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-brand-cream/60">
              Send your sales file plus your inventory file. We match products by name and show where cash is stuck.
              No sign-up, no credit card, no customer data needed.
            </p>
          </div>
          <GuestAuditUploader />
        </div>
      </section>

      <section className="border-y border-brand-night/10 bg-brand-cream px-5 py-12 text-brand-night md:px-8">
        <div className="mx-auto grid max-w-7xl gap-4 md:grid-cols-3">
          {[
            [FileSpreadsheet, 'Send two files', 'Sales export + inventory export. No customer names needed.'],
            [TrendingUp, 'Get a Money Audit', 'Dead stock, stockout risk, margin leakage, and value estimate.'],
            [MessageCircle, 'Approve fixes', 'Owner actions delivered through WhatsApp, not daily dashboards.'],
          ].map(([Icon, title, body]) => {
            const LucideIcon = Icon as typeof FileSpreadsheet;
            return (
              <div key={title as string} className="rounded-3xl border border-brand-night/10 bg-brand-cream-dark p-6">
                <LucideIcon className="mb-4 h-6 w-6 text-whatsapp-deep" />
                <h3 className="font-serif text-2xl font-black">{title as string}</h3>
                <p className="mt-3 leading-7 text-brand-night/62">{body as string}</p>
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
            <div className="rounded-3xl border border-brand-cream/10 bg-brand-cream/[0.04] p-6">
              <NazmakMark className="mb-5 h-12 w-12" />
              <p className="font-mono text-xs uppercase tracking-[.22em] text-brand-amber">Company</p>
              <h3 className="mt-3 font-serif text-3xl font-black">Nazmak</h3>
              <p className="mt-3 leading-7 text-brand-cream/58">Builds recovery systems that bring order to Saudi business operations.</p>
            </div>
            <div className="rounded-3xl border border-brand-amber/25 bg-brand-amber/10 p-6">
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-amber font-serif text-xl font-black text-brand-night">N</div>
              <p className="font-mono text-xs uppercase tracking-[.22em] text-brand-amber">Product</p>
              <h3 className="mt-3 font-serif text-3xl font-black">NazmOS</h3>
              <p className="mt-3 leading-7 text-brand-cream/58">The Retail Recovery System that finds cash leakage and sends owner actions.</p>
            </div>
          </div>
        </div>
      </section>

      <section id="audit" className="bg-brand-cream px-5 py-20 text-brand-night md:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="mb-12 max-w-3xl">
            <SectionLabel>What NazmOS watches</SectionLabel>
            <h2 className="mt-4 font-serif text-4xl font-black tracking-[-.03em] md:text-6xl">Four ways stores lose money quietly.</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {watchCards.map(([title, body, Icon, color], i) => {
              const LucideIcon = Icon as typeof WalletCards;
              return (
                <div key={title as string} className="rounded-3xl border border-brand-night/10 bg-brand-cream-dark p-6">
                  <div className="mb-10 flex items-center justify-between">
                    <span className="font-mono text-xs text-brand-night/40">0{i + 1}</span>
                    <LucideIcon className="h-5 w-5" style={{ color: color as string }} />
                  </div>
                  <h3 className="font-serif text-2xl font-black">{title as string}</h3>
                  <p className="mt-4 leading-7 text-brand-night/62">{body as string}</p>
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
            <p className="mt-6 max-w-xl text-lg leading-8 text-brand-cream/62">Use the tabs to see the three moments that matter: audit, approval, and weekly proof.</p>
            <div className="mt-8 flex flex-wrap gap-2">
              {demoTabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveDemo(tab.id)}
                  className={`rounded-full px-4 py-2 text-sm font-bold transition ${activeDemo === tab.id ? 'bg-brand-amber text-brand-night' : 'border border-brand-cream/10 text-brand-cream/62 hover:bg-brand-cream/5 hover:text-brand-cream'}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
          <DemoPanel active={activeDemo} />
        </div>
      </section>

      <section id="pricing" className="bg-brand-cream px-5 py-20 text-brand-night md:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="mb-10 max-w-3xl">
            <SectionLabel>Start small, prove value</SectionLabel>
            <h2 className="mt-4 font-serif text-4xl font-black md:text-6xl">Simple pricing after we prove value.</h2>
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            {pricingCards.map(([title, price, body, features]) => (
              <div key={title as string} className="rounded-3xl border border-brand-night/10 bg-brand-cream-dark p-7">
                <h3 className="font-serif text-2xl font-black">{title as string}</h3>
                <p className="mt-4 font-serif text-3xl font-black text-whatsapp-deep">{price as string}</p>
                <p className="mt-4 leading-7 text-brand-night/62">{body as string}</p>
                <ul className="mt-6 space-y-2">
                  {(features as string[]).map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm text-brand-night/65">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-whatsapp-deep" /> {feature}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-5 py-16 md:px-8">
        <div className="mx-auto max-w-7xl rounded-[2rem] border border-brand-cream/10 bg-brand-cream/[0.03] p-8 md:p-10">
          <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-success/10 px-3 py-2 text-xs font-bold text-success">
                <ShieldCheck className="h-4 w-4" /> Free tier honesty
              </div>
              <h2 className="font-serif text-3xl font-black md:text-5xl">Free proves value. Paid plans unlock continuous recovery.</h2>
              <p className="mt-4 max-w-3xl leading-7 text-brand-cream/60">Free shows your Money Audit. Paid plans unlock weekly recovery reports, live approvals, and Recovery Match between nearby stores.</p>
            </div>
            <Link href="/register?intent=free-audit" className="inline-flex items-center justify-center gap-2 rounded-2xl bg-brand-amber px-6 py-4 font-bold text-brand-night hover:bg-brand-gold-soft">
              Get a Free Money Audit <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="px-5 py-12 md:px-8">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 border-t border-brand-cream/10 pt-8 md:flex-row md:items-center">
          <div className="flex items-center gap-3">
            <NazmakMark className="h-10 w-10" />
            <div>
              <p className="font-serif text-2xl font-black">nazmak</p>
              <p className="mt-1 text-sm text-brand-cream/50">Company behind NazmOS Retail Recovery.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Link href="/privacy" className="text-sm font-semibold text-brand-cream/45 hover:text-brand-cream">Privacy</Link>
            <Link href="/terms" className="text-sm font-semibold text-brand-cream/45 hover:text-brand-cream">Terms</Link>
            <Link href="/register?intent=free-audit" className="inline-flex items-center gap-2 rounded-2xl bg-brand-amber px-5 py-3 font-bold text-brand-night">
              Get a Free Money Audit <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
