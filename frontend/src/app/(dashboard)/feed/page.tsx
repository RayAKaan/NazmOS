"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";

type AgentAction = {
  id: string;
  action_type: string;
  status: string;
  confidence: number;
  title: string;
  title_ar?: string;
  summary: string;
  summary_ar?: string;
  payload: any;
  estimated_value_sar?: number;
  created_at: string;
  can_approve: boolean;
};

export default function FeedPage() {
  const [items, setItems] = useState<AgentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const { businessId } = useAppStore();

  const load = useCallback(async () => {
    if (!businessId) return;
    try {
      const res = await api.get("/agent/feed", { params: { business_id: businessId } });
      setItems(res.data.items || []);
    } catch (e) {
      // demo fallback
      setItems([
        {
          id: "demo-1",
          action_type: "restock",
          status: "pending_approval",
          confidence: 0.92,
          title: "Restock Almarai Milk 1L",
          title_ar: "إعادة طلب حليب المراعي ١ لتر",
          summary: "Stock runs out in 1.8 days – Order 135 units – 1,012 SAR – ETA Thursday",
          summary_ar: "المخزون ينتهي خلال 1.8 يوم – اطلب 135 – 1,012 ر.س – التوصيل الخميس",
          payload: { quantity: 135, estimated_cost_sar: 1012 },
          estimated_value_sar: 1012,
          created_at: new Date().toISOString(),
          can_approve: true,
        },
        {
          id: "demo-2",
          action_type: "expiry_alert",
          status: "pending_approval",
          confidence: 0.95,
          title: "Expiry Alert – Panadol Extra",
          title_ar: "تنبيه انتهاء صلاحية – بانادول إكسترا",
          summary: "Batch #RX4421 expires in 47 days – 24 units – Discount to clear?",
          summary_ar: "التشغيلة RX4421 تنتهي خلال 47 يوم – 24 وحدة – خصم للتصريف؟",
          payload: { quantity: 24 },
          created_at: new Date().toISOString(),
          can_approve: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => { load(); }, [load]);

  const act = async (id: string, action: "approve" | "reject") => {
    try {
      const path =
        action === "approve"
          ? `/agent/actions/${id}/approve`
          : `/agent/actions/${id}/reject`;
      await api.post(path, {}, { params: { business_id: businessId } });
    } catch {}
    setItems(items.filter(i => i.id !== id));
  };

  return (
    <div className="p-6 md:p-8 max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Nazm – Attention Feed</h1>
        <p className="text-text-muted text-sm">نظم – كل ما يحتاج موافقتك، مرتب حسب الأهمية</p>
      </div>

      {loading && <div className="text-text-muted">Loading Nazm…</div>}

      {!loading && items.length === 0 && (
        <div className="bg-surface border border-border rounded-2xl p-12 text-center">
          <div className="text-4xl mb-3">✅</div>
          <div className="font-semibold mb-1">All clear – لا يوجد شيء يحتاج انتباهك</div>
          <div className="text-sm text-text-muted">Nazm is watching your inventory 24/7</div>
        </div>
      )}

      <div className="space-y-3">
        {items.map((it) => (
          <div key={it.id} className="bg-surface border border-border rounded-2xl p-5 hover:border-accent-blue/30 transition-colors">
            <div className="flex items-start justify-between mb-2">
              <div className="text-xs uppercase tracking-wider text-text-muted">
                {it.action_type.replace("_", " ")} • confidence {(it.confidence * 100).toFixed(0)}%
              </div>
              <div className="text-xs text-text-muted">
                {new Date(it.created_at).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" })}
              </div>
            </div>
            <div className="font-semibold text-lg mb-1">{it.title_ar || it.title}</div>
            <div className="text-sm text-text-secondary mb-1">{it.summary_ar || it.summary}</div>
            {it.summary_ar && it.summary !== it.summary_ar && (
              <div className="text-xs text-text-muted mb-3">{it.summary}</div>
            )}
            {it.estimated_value_sar && (
              <div className="text-sm text-text-muted mb-3">﷼ {it.estimated_value_sar.toLocaleString("ar-SA")} SAR</div>
            )}
            {it.can_approve ? (
              <div className="flex gap-2">
                <button
                  onClick={() => act(it.id, "approve")}
                  className="flex-1 bg-accent-green text-white py-2.5 rounded-xl font-medium hover:opacity-90"
                >
                  ✅ Approve – موافق
                </button>
                <button
                  onClick={() => act(it.id, "reject")}
                  className="px-4 py-2.5 bg-surface-hover rounded-xl text-text-secondary hover:text-text-primary"
                >
                  Reject
                </button>
              </div>
            ) : (
              <div className="text-xs text-text-muted">Info only – لا يحتاج موافقة</div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-8 text-center text-xs text-text-muted">
        Autonomy dial: <a href="/settings/autonomy" className="text-accent-blue hover:underline">Settings → التحكم الذاتي</a>
      </div>
    </div>
  );
}
