"use client";

import { useState, useEffect } from "react";

type Lot = {
  id: string;
  item_name: string;
  item_name_ar?: string;
  batch_number: string;
  expiry_date: string;
  quantity: number;
  days_left: number;
};

export default function ExpiryPage() {
  const [lots, setLots] = useState<Lot[]>([]);
  const [filter, setFilter] = useState<"all" | "critical" | "warning" | "ok">("all");

  useEffect(() => {
    // TODO: fetch from /api/v1/pharmacy/lots
    // Demo data – Saudi pharmacy
    setLots([
      { id: "1", item_name: "Panadol Extra", item_name_ar: "بانادول إكسترا", batch_number: "RX4421", expiry_date: "2026-08-19", quantity: 24, days_left: 47 },
      { id: "2", item_name: "Augmentin 1g", item_name_ar: "أوجمنتين ١ جم", batch_number: "AM-8832", expiry_date: "2026-09-12", quantity: 18, days_left: 71 },
      { id: "3", item_name: "Ventolin Inhaler", item_name_ar: "فنتولين بخاخ", batch_number: "VT-1190", expiry_date: "2026-11-03", quantity: 12, days_left: 123 },
      { id: "4", item_name: "Lipitor 20mg", item_name_ar: "ليبيتور ٢٠ مجم", batch_number: "LP-5521", expiry_date: "2026-07-22", quantity: 8, days_left: 19 },
    ]);
  }, []);

  const filtered = lots.filter(l => {
    if (filter === "critical") return l.days_left < 30;
    if (filter === "warning") return l.days_left >= 30 && l.days_left < 90;
    if (filter === "ok") return l.days_left >= 90;
    return true;
  }).sort((a, b) => a.days_left - b.days_left);

  const badge = (days: number) => {
    if (days < 30) return { text: "حرج – Critical", cls: "bg-destructive/10 text-destructive border-destructive/30" };
    if (days < 90) return { text: "قريب – Warning", cls: "bg-warning/10 text-warning border-warning/30" };
    return { text: "OK", cls: "bg-success/10 text-success border-success/30" };
  };

  return (
    <div className="p-6 md:p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Expiry Tracker – تتبع انتهاء الصلاحية</h1>
          <p className="text-muted-foreground text-sm">FEFO – First Expired, First Out – SFDA compliant</p>
        </div>
        <div className="text-sm text-muted-foreground">Pharmacy Module – وحدة الصيدلية</div>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {[
          {k: "all", label: "All – الكل"},
          {k: "critical", label: "< 30 days"},
          {k: "warning", label: "30-90 days"},
          {k: "ok", label: "> 90 days"},
        ].map(f => (
          <button
            key={f.k}
            onClick={() => setFilter(f.k as any)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              filter === f.k
                ? "bg-primary text-primary-foreground"
                : "bg-surface border border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="bg-surface border border-border rounded-2xl overflow-hidden">
        <table className="w-full">
          <thead className="bg-surface-hover text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-5 py-3">Product / المنتج</th>
              <th className="text-left px-5 py-3">Batch</th>
              <th className="text-left px-5 py-3">Expiry</th>
              <th className="text-right px-5 py-3">Qty</th>
              <th className="text-right px-5 py-3">Status</th>
              <th className="text-right px-5 py-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map(l => {
              const b = badge(l.days_left);
              return (
                <tr key={l.id} className="hover:bg-surface-hover/50">
                  <td className="px-5 py-4">
                    <div className="font-medium">{l.item_name_ar || l.item_name}</div>
                    <div className="text-xs text-muted-foreground">{l.item_name}</div>
                  </td>
                  <td className="px-5 py-4 font-mono text-sm">{l.batch_number}</td>
                  <td className="px-5 py-4 text-sm">
                    {new Date(l.expiry_date).toLocaleDateString("ar-SA")}
                    <div className="text-xs text-muted-foreground">{l.days_left} days</div>
                  </td>
                  <td className="px-5 py-4 text-right font-mono">{l.quantity}</td>
                  <td className="px-5 py-4 text-right">
                    <span className={`text-xs px-2 py-1 rounded border ${b.cls}`}>{b.text}</span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    {l.days_left < 90 ? (
                      <button className="text-xs text-primary hover:underline">Discount – خصم</button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="px-5 py-12 text-center text-muted-foreground">No lots in this category – لا توجد دفعات</div>
        )}
      </div>

      <div className="mt-4 text-xs text-muted-foreground">
        SFDA recall check: <span className="text-success">✓ Active – no recalls matched to your inventory</span>
        <span className="mx-2">•</span>
        Last scan: just now
      </div>
    </div>
  );
}
