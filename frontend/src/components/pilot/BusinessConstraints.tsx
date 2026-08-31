"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

export default function BusinessConstraints({ businessId }: { businessId: string }) {
  const [constraints, setConstraints] = useState<any>({});
  const [saved, setSaved] = useState(false);
  useEffect(() => { api.get(`/businesses/current/constraints`).then(r => setConstraints(r.data.constraints || {})).catch(() => {}); }, [businessId]);
  async function save() { await api.patch(`/businesses/current/constraints`, { cash_budget: constraints.cash_budget == null || constraints.cash_budget === "" ? null : Number(constraints.cash_budget), minimum_margin: constraints.minimum_margin == null || constraints.minimum_margin === "" ? null : Number(constraints.minimum_margin), max_discount: constraints.max_discount == null || constraints.max_discount === "" ? null : Number(constraints.max_discount), strategic_products: constraints.strategic_products || [], blocked_discount_products: constraints.blocked_discount_products || [] }); setSaved(true); setTimeout(() => setSaved(false), 1800); }
  return <section className="rounded-2xl border border-border bg-surface p-6"><h2 className="text-xl font-bold">Business guardrails</h2><p className="text-sm text-muted-foreground">NazmOS applies these constraints before recommendations are finalized.</p><div className="mt-4 grid gap-4 md:grid-cols-3"><label className="text-sm">Cash budget<input className="mt-1 w-full rounded-lg border border-border bg-transparent p-2" value={constraints.cash_budget ?? ""} onChange={e => setConstraints({...constraints,cash_budget:e.target.value})} placeholder="SAR" /></label><label className="text-sm">Minimum margin<input className="mt-1 w-full rounded-lg border border-border bg-transparent p-2" value={constraints.minimum_margin ?? ""} onChange={e => setConstraints({...constraints,minimum_margin:e.target.value})} placeholder="0.20" /></label><label className="text-sm">Maximum discount %<input className="mt-1 w-full rounded-lg border border-border bg-transparent p-2" value={constraints.max_discount ?? ""} onChange={e => setConstraints({...constraints,max_discount:e.target.value})} placeholder="20" /></label></div><button onClick={save} className="mt-4 rounded-xl border border-brand-amber px-4 py-2 text-sm font-bold">{saved ? "Saved" : "Save guardrails"}</button></section>;
}
