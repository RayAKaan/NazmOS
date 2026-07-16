"use client";

import { useState, useEffect } from "react";

type Supplier = {
  id: string;
  name_ar: string;
  name_en: string;
  city: string;
  category: string;
  phone?: string;
  whatsapp_number?: string;
  lead_time_days: number;
  total_orders: number;
  total_volume_sar: number;
};

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  useEffect(() => {
    // TODO: GET /api/v1/suppliers
    setSuppliers([
      { id: "1", name_ar: "المراعي", name_en: "Almarai", city: "Riyadh", category: "dairy", phone: "+966 11 470 0005", whatsapp_number: "+966500000001", lead_time_days: 1, total_orders: 47, total_volume_sar: 84500 },
      { id: "2", name_ar: "نادك", name_en: "Nadec", city: "Riyadh", category: "dairy", phone: "+966 11 202 7777", whatsapp_number: "+966500000002", lead_time_days: 2, total_orders: 22, total_volume_sar: 32100 },
      { id: "3", name_ar: "الدواء", name_en: "Al-Dawaa Distributor", city: "Buraidah", category: "pharma", phone: "+966 16 385 1111", whatsapp_number: "+966500000003", lead_time_days: 2, total_orders: 31, total_volume_sar: 127400 },
      { id: "4", name_ar: "النهدي للتوزيع", name_en: "Nahdi Distribution", city: "Jeddah", category: "pharma", phone: "+966 12 653 3333", whatsapp_number: "+966500000004", lead_time_days: 3, total_orders: 12, total_volume_sar: 58900 },
      { id: "5", name_ar: "مؤسسة التموين الغذائي", name_en: "Food Supply Est.", city: "Riyadh", category: "food_wholesale", phone: "+966 11 405 6677", whatsapp_number: "+966500000005", lead_time_days: 1, total_orders: 56, total_volume_sar: 94300 },
    ]);
  }, []);

  const totalVolume = suppliers.reduce((s, x) => s + x.total_volume_sar, 0);

  return (
    <div className="p-6 md:p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Suppliers – الموردين</h1>
          <p className="text-text-muted text-sm">Your order network – aggregate volume builds negotiating leverage</p>
        </div>
        <div className="text-right">
          <div className="text-xs text-text-muted">Total routed (all shops)</div>
          <div className="text-xl font-mono font-bold">﷼ {totalVolume.toLocaleString("ar-SA")} SAR</div>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-2xl overflow-hidden">
        <table className="w-full">
          <thead className="bg-surface-hover text-xs uppercase tracking-wider text-text-muted">
            <tr>
              <th className="text-left px-5 py-3">Supplier</th>
              <th className="text-left px-5 py-3">City</th>
              <th className="text-left px-5 py-3">Category</th>
              <th className="text-right px-5 py-3">Lead</th>
              <th className="text-right px-5 py-3">Orders</th>
              <th className="text-right px-5 py-3">Volume SAR</th>
              <th className="text-right px-5 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {suppliers.map(s => (
              <tr key={s.id} className="hover:bg-surface-hover/50">
                <td className="px-5 py-4">
                  <div className="font-medium">{s.name_ar}</div>
                  <div className="text-xs text-text-muted">{s.name_en}</div>
                </td>
                <td className="px-5 py-4 text-sm">{s.city}</td>
                <td className="px-5 py-4 text-xs">
                  <span className="px-2 py-1 rounded bg-surface-hover text-text-muted">{s.category}</span>
                </td>
                <td className="px-5 py-4 text-right text-sm">{s.lead_time_days}d</td>
                <td className="px-5 py-4 text-right font-mono">{s.total_orders}</td>
                <td className="px-5 py-4 text-right font-mono">﷼ {s.total_volume_sar.toLocaleString("ar-SA")}</td>
                <td className="px-5 py-4 text-right">
                  {s.whatsapp_number && (
                    <a
                      href={`https://wa.me/${s.whatsapp_number.replace(/[^0-9]/g, "")}`}
                      target="_blank"
                      className="text-xs text-accent-green hover:underline"
                    >
                      WhatsApp →
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 bg-accent-blue/5 border border-accent-blue/20 rounded-xl p-4 text-sm">
        <b>Network effect – تأثير الشبكة:</b> Once NazmOS routes orders from 30+ shops to the same distributor, we negotiate better prices / faster fulfillment for all our shops. You benefit automatically – no extra work.
        <br />
        <span className="text-text-muted">حاليا: تتبع فقط – التفاوض يبدأ عند 30 متجر نشط</span>
      </div>
    </div>
  );
}
