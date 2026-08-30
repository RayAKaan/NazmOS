"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

export default function RecommendationInbox({ businessId }: { businessId: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.get(`/pilot/recommendations?business_id=${businessId}`)
      .then(r => { if (live) setItems(r.data.recommendations || []); })
      .catch(e => { if (live) setError(e?.response?.data?.detail || "Could not load recommendations"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [businessId]);
  if (loading) return <section className="rounded-2xl border border-border p-6 text-sm text-text-secondary">Loading recommendations…</section>;
  if (error) return <section className="rounded-2xl border border-status-error/30 p-6 text-sm text-status-error">{error}</section>;
  return <section className="rounded-2xl border border-border bg-surface p-6">
    <div className="flex items-center justify-between"><div><h2 className="text-xl font-bold">Today’s decisions</h2><p className="text-sm text-text-secondary">Evidence-backed recommendations. Approval remains required in pilot mode.</p></div><span className="text-sm text-text-secondary">{items.length} items</span></div>
    <div className="mt-5 space-y-3">{items.map(item => <details key={item.id} className="rounded-xl border border-border p-4"><summary className="cursor-pointer font-semibold">{item.title}</summary><div className="mt-3 grid gap-2 text-sm md:grid-cols-3"><div><span className="text-text-secondary">Action</span><div>{item.action_type}</div></div><div><span className="text-text-secondary">Recoverable range</span><div>SAR {Number(item.recoverable_value_low_sar || 0).toLocaleString()}–{Number(item.recoverable_value_high_sar || 0).toLocaleString()}</div></div><div><span className="text-text-secondary">Mode</span><div>{item.execution_mode}</div></div></div>{item.description && <p className="mt-3 text-sm text-text-secondary">{item.description}</p>}</details>)}</div>
    {items.length === 0 && <p className="mt-5 text-sm text-text-secondary">No action required from the current audit.</p>}
  </section>;
}
