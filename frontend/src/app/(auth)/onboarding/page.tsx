"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="w-full max-w-xl bg-surface border border-border rounded-2xl p-8">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-accent-blue mx-auto flex items-center justify-center text-white font-bold text-2xl mb-3">ن</div>
          <h1 className="text-2xl font-bold">مرحبا بك في NazmOS</h1>
          <p className="text-text-muted">Welcome to NazmOS KSA</p>
        </div>

        {step === 1 && (
          <div className="space-y-5">
            <h2 className="text-lg font-semibold">Step 1/3 – Create your admin account</h2>
            <p className="text-sm text-text-muted">Go to Register and create your store owner account. This is stored locally on YOUR server only.</p>
            <Link href="/register" className="block w-full text-center bg-accent-blue text-white py-3 rounded-xl font-medium hover:opacity-90">
              Create Admin Account →
            </Link>
            <button onClick={() => setStep(2)} className="w-full text-sm text-text-muted underline">I already have an account – next</button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5">
            <h2 className="text-lg font-semibold">Step 2/3 – Upload your sales file</h2>
            <ul className="text-sm text-text-muted space-y-2 list-disc pl-5">
              <li>CSV / Excel from your POS or cashier export</li>
              <li>Required columns: product_name, quantity, price, date</li>
              <li>We auto-detect columns – you just confirm mapping</li>
              <li>All data stays on your machine – PDPL compliant</li>
            </ul>
            <Link href="/upload" className="block w-full text-center bg-accent-blue text-white py-3 rounded-xl font-medium hover:opacity-90">
              Go to Upload →
            </Link>
            <button onClick={() => setStep(3)} className="w-full text-sm text-text-muted underline">Skip – I uploaded already</button>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5">
            <h2 className="text-lg font-semibold">Step 3/3 – You’re ready</h2>
            <div className="bg-surface-hover rounded-xl p-4 text-sm space-y-2">
              <p>✅ <b>Dashboard</b> – sales, profit, KPIs – SAR</p>
              <p>✅ <b>Inventory</b> – dead stock, reorder list</p>
              <p>✅ <b>Forecast</b> – Prophet, Ramadan / Eid / National Day aware</p>
              <p>✅ <b>Alerts</b> – Email & in-app low-stock (WhatsApp – coming soon)</p>
            </div>
            <button onClick={() => router.push("/dashboard")} className="w-full bg-accent-green text-white py-3 rounded-xl font-medium hover:opacity-90">
              Open Dashboard →
            </button>
            <p className="text-xs text-center text-text-muted">Support WhatsApp: +966 5X XXX XXXX • support@nazmos.sa</p>
          </div>
        )}

        <div className="flex justify-center gap-2 mt-6">
          {[1,2,3].map(s => (
            <div key={s} className={`w-2 h-2 rounded-full ${s===step ? 'bg-accent-blue' : 'bg-border'}`} />
          ))}
        </div>
      </div>
    </div>
  );
}
