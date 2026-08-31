"use client";

import { useState } from "react";
import { Users, Award, BadgeCheck, Share2 } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

const partnerTypes = [
  { value: "accountant", label: "Accountant / محاسب", desc: "Help merchants reconcile books and track cash flow." },
  { value: "advisor", label: "Monshaat Advisor / مستشار", desc: "Advise Saudi SMEs on growth, grants, and compliance." },
  { value: "consultant", label: "Business Consultant / مستشار أعمال", desc: "Implement NazmOS for retail, pharmacy, and F&B clients." },
  { value: "auditor", label: "Compliance Auditor / مدقق", desc: "Review processes, inventory, and PDPL readiness." },
  { value: "fintech", label: "Bank / Fintech Partner / شريك مالي", desc: "Embed working-capital offers inside NazmOS insights." },
];

export default function PartnersPage() {
  const [form, setForm] = useState({
    partner_type: "accountant",
    name: "",
    email: "",
    phone: "",
    city: "",
    cr_number: "",
    monshaat_certified: false,
    bank_iban: "",
  });
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/partners/apply", form);
      setSubmitted(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not submit application.");
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <section className="border-b border-border bg-surface px-6 py-12 text-center">
        <div className="mx-auto max-w-2xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-amber/30 bg-brand-amber/10 px-3 py-2 text-xs font-bold uppercase tracking-[0.22em] text-brand-amber">
            <Share2 className="h-4 w-4" /> Partner Program
          </div>
          <h1 className="mt-5 font-serif text-4xl font-black tracking-tight md:text-5xl">
            Grow with NazmOS
          </h1>
          <p className="mt-4 text-muted-foreground">
            Accountants, Monshaat advisors, consultants, auditors, and fintechs — refer merchants, earn commissions, and co-deliver value.
          </p>
        </div>
      </section>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="grid gap-4 md:grid-cols-3">
          <Value icon={Users} title="Refer" body="Introduce merchants who need inventory intelligence." />
          <Value icon={Award} title="Earn" body="Track conversions and receive commission on paid plans." />
          <Value icon={BadgeCheck} title="Certify" body="Become a verified NazmOS implementation partner." />
        </div>

        {submitted ? (
          <div className="mt-10 rounded-2xl border border-brand-green/30 bg-brand-green/10 p-8 text-center">
            <h2 className="text-2xl font-bold text-brand-cream">Application received</h2>
            <p className="mt-2 text-muted-foreground">
              The Nazmak team will review your profile and send your partner referral code within 2 business days.
            </p>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-10 space-y-5 rounded-2xl border border-border bg-surface p-6 md:p-8">
            <h2 className="text-xl font-bold">Apply to become a partner</h2>
            {error && <div className="rounded-xl border border-brand-red/30 bg-brand-red/10 p-3 text-sm text-brand-red-light">{error}</div>}

            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Full name / اسم" value={form.name} onChange={(v) => setForm({ ...form, name: v })} required />
              <Field label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} required />
              <Field label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} />
              <Field label="City / المدينة" value={form.city} onChange={(v) => setForm({ ...form, city: v })} />
              <Field label="CR Number (optional)" value={form.cr_number} onChange={(v) => setForm({ ...form, cr_number: v })} />
              <Field label="Bank IBAN (optional)" value={form.bank_iban} onChange={(v) => setForm({ ...form, bank_iban: v })} />
            </div>

            <label className="block text-sm font-medium text-muted-foreground">Partner type</label>
            <div className="grid gap-3 md:grid-cols-2">
              {partnerTypes.map((pt) => (
                <label
                  key={pt.value}
                  className={cn(
                    "cursor-pointer rounded-xl border p-4 transition",
                    form.partner_type === pt.value
                      ? "border-primary bg-primary/10"
                      : "border-border bg-brand-cream/[0.02] hover:border-brand-cream/20"
                  )}
                >
                  <input
                    type="radio"
                    name="partner_type"
                    value={pt.value}
                    checked={form.partner_type === pt.value}
                    onChange={(e) => setForm({ ...form, partner_type: e.target.value })}
                    className="sr-only"
                  />
                  <p className="font-bold text-brand-cream">{pt.label}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{pt.desc}</p>
                </label>
              ))}
            </div>

            <label className="flex items-center gap-3 rounded-xl border border-border bg-brand-cream/[0.02] p-4 text-sm">
              <input
                type="checkbox"
                checked={form.monshaat_certified}
                onChange={(e) => setForm({ ...form, monshaat_certified: e.target.checked })}
              />
              <span>Monshaat certified / معتمد من منشآت</span>
            </label>

            <button
              type="submit"
              className="w-full rounded-xl bg-primary py-3 font-bold text-primary-foreground hover:opacity-90"
            >
              Submit application
            </button>
          </form>
        )}
      </main>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", required }: { label: string; value: string; onChange: (v: string) => void; type?: string; required?: boolean }) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <input
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-border bg-brand-night/30 px-3 py-2 text-brand-cream outline-none focus:border-primary"
      />
    </label>
  );
}

function Value({ icon: Icon, title, body }: { icon: React.ElementType; title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <Icon className="h-6 w-6 text-primary" />
      <h3 className="mt-3 font-bold text-brand-cream">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </div>
  );
}
