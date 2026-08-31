"use client";

import { Truck, RefreshCw } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { useSuppliers } from "@/hooks/useSuppliers";

export default function SuppliersPage() {
  const { suppliers, isLoading, error, refetch } = useSuppliers();

  const totalVolume = suppliers.reduce((s, x) => s + x.total_volume_sar, 0);

  if (isLoading) {
    return (
      <div className="p-6 md:p-8 max-w-5xl">
        <div className="h-8 w-56 bg-surface-hover animate-pulse rounded mb-2" />
        <div className="h-4 w-80 bg-surface-hover animate-pulse rounded mb-6" />
        <div className="h-64 bg-surface border border-border rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 md:p-8 max-w-5xl">
        <div className="bg-destructive/10 border border-destructive/30 rounded-xl p-6 text-center">
          <p className="font-medium text-destructive mb-4">{error}</p>
          <button
            onClick={refetch}
            className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-xl text-sm font-medium hover:bg-primary/90"
          >
            <RefreshCw className="w-4 h-4" /> Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Suppliers – الموردين</h1>
          <p className="text-muted-foreground text-sm">Your order network – aggregate volume builds negotiating leverage</p>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted-foreground">Total routed (all shops)</div>
          <div className="text-xl font-mono font-bold">﷼ {totalVolume.toLocaleString("ar-SA")} SAR</div>
        </div>
      </div>

      {suppliers.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="No suppliers yet"
          description="Import your purchase orders to build your supplier network. NazmOS aggregates volume across shops to negotiate better prices."
          actions={[{ label: "Upload files", href: "/upload", primary: true }]}
        />
      ) : (
        <div className="bg-surface border border-border rounded-2xl overflow-hidden">
          <table className="w-full">
            <thead className="bg-surface-hover text-xs uppercase tracking-wider text-muted-foreground">
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
                    <div className="text-xs text-muted-foreground">{s.name_en}</div>
                  </td>
                  <td className="px-5 py-4 text-sm">{s.city}</td>
                  <td className="px-5 py-4 text-xs">
                    <span className="px-2 py-1 rounded bg-surface-hover text-muted-foreground">{s.category}</span>
                  </td>
                  <td className="px-5 py-4 text-right text-sm">{s.lead_time_days}d</td>
                  <td className="px-5 py-4 text-right font-mono">{s.total_orders}</td>
                  <td className="px-5 py-4 text-right font-mono">﷼ {s.total_volume_sar.toLocaleString("ar-SA")}</td>
                  <td className="px-5 py-4 text-right">
                    {s.whatsapp_number && (
                      <a
                        href={`https://wa.me/${s.whatsapp_number.replace(/[^0-9]/g, "")}`}
                        target="_blank"
                        className="text-xs text-success hover:underline"
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
      )}

      <div className="mt-4 bg-primary/5 border border-border/20 rounded-xl p-4 text-sm">
        <b>Network effect – تأثير الشبكة:</b> Once NazmOS routes orders from 30+ shops to the same distributor, we negotiate better prices / faster fulfillment for all our shops. You benefit automatically – no extra work.
        <br />
        <span className="text-muted-foreground">حاليا: تتبع فقط – التفاوض يبدأ عند 30 متجر نشط</span>
      </div>
    </div>
  );
}
