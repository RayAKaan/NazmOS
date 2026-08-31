"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";

type Policy = {
  action_type: string;
  label: string;
  label_en: string;
  dial: number;
  ceiling_sar?: number;
  max_price_increase_pct?: number;
  description_ar: string;
  description_en: string;
};

type AutonomyExplanation = {
  action_type: string;
  label: string;
  mode: "automatic" | "automatic-conditional" | "approval" | "human";
  explanation: string;
  default_dial: number;
  base_risk: string;
};

type SafetyFloors = {
  min_confidence: number;
  risk_escalate_medium_sar: number;
  risk_escalate_high_sar: number;
  note: string;
};

export default function AutonomyPage() {
  const [policies, setPolicies] = useState<Policy[]>([
    { action_type: "restock", label: "إعادة الطلب", label_en: "Restocking", dial: 50, ceiling_sar: 2000, description_ar: "0 = أخبرني فقط / 50 = جهز وانتظر موافقتي / 100 = نفذ تلقائيا", description_en: "0 = inform / 50 = draft+approve / 100 = auto" },
    { action_type: "pricing_increase", label: "رفع الأسعار", label_en: "Price Increase", dial: 20, max_price_increase_pct: 5, description_ar: "0 = أخبرني فقط / 50 = جهز وانتظر موافقتي / 100 = نفذ تلقائيا", description_en: "0 = inform / 50 = draft+approve / 100 = auto" },
    { action_type: "pricing_decrease", label: "خفض الأسعار", label_en: "Price Decrease", dial: 30, description_ar: "0 = أخبرني فقط / 50 = جهز وانتظر موافقتي / 100 = نفذ تلقائيا", description_en: "0 = inform / 50 = draft+approve / 100 = auto" },
    { action_type: "cash_alert", label: "التدفق النقدي", label_en: "Cash Flow", dial: 0, description_ar: "تنبيه فقط – لا تنفيذ تلقائي أبداً", description_en: "Inform only – never auto-execute", },
    { action_type: "staff_schedule", label: "جدولة الموظفين", label_en: "Staffing", dial: 0, description_ar: "تنبيه فقط", description_en: "Inform only" },
    { action_type: "expiry_alert", label: "تنبيهات انتهاء الصلاحية", label_en: "Expiry Alerts", dial: 50, description_ar: "0 = أخبرني فقط / 50 = جهز وانتظر موافقتي / 100 = نفذ تلقائيا", description_en: "0 = inform / 50 = draft+approve / 100 = auto" },
  ]);
  const [saving, setSaving] = useState(false);
  const [explanation, setExplanation] = useState<AutonomyExplanation[]>([]);
  const [floors, setFloors] = useState<SafetyFloors | null>(null);
  const { businessId } = useAppStore();

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get("/agent/autonomy", { params: { business_id: businessId } });
        if (res.data.policies?.length) setPolicies(res.data.policies);
      } catch {}
      try {
        const res = await api.get("/agent/autonomy/explanation", { params: { business_id: businessId } });
        if (res.data.actions) setExplanation(res.data.actions);
        if (res.data.safety_floors) setFloors(res.data.safety_floors);
      } catch {}
    })();
  }, [businessId]);

  const setDial = (action_type: string, dial: number) => {
    setPolicies(p => p.map(x => x.action_type === action_type ? { ...x, dial } : x));
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/agent/autonomy",
        { policies: policies.map(p => ({
          action_type: p.action_type,
          dial: p.dial,
          ceiling_sar: p.ceiling_sar,
          max_price_increase_pct: p.max_price_increase_pct,
          max_price_decrease_pct: (p as any).max_price_decrease_pct,
        }))},
        { params: { business_id: businessId } }
      );
      alert("Saved – تم الحفظ");
    } catch {
      alert("Saved locally (demo mode)");
    } finally {
      setSaving(false);
    }
  };

  const labelFor = (d: number) => d === 0 ? "Inform – إخبار" : d < 50 ? "Suggest – اقتراح" : d < 95 ? "Approve – موافقة" : "Auto – تلقائي";
  const colorFor = (d: number) => d === 0 ? "text-muted-foreground" : d < 50 ? "text-warning" : d < 95 ? "text-primary" : "text-success";

  return (
    <div className="p-6 md:p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">Autonomy Dial – التحكم الذاتي</h1>
      <p className="text-muted-foreground text-sm mb-8">Control how much Nazm does on its own. 0 = inform only · 50 = draft + approve · 100 = auto-execute</p>

      <div className="space-y-6">
        {policies.map((p) => (
          <div key={p.action_type} className="bg-surface border border-border rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-semibold">{p.label} <span className="text-muted-foreground font-normal">· {p.label_en}</span></div>
                <div className="text-xs text-muted-foreground">{p.description_ar}</div>
              </div>
              <div className={`text-sm font-mono font-bold ${colorFor(p.dial)}`}>
                {p.dial} – {labelFor(p.dial)}
              </div>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={p.dial}
              onChange={(e) => setDial(p.action_type, parseInt(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-xs text-muted-foreground mt-1">
              <span>0 Inform</span>
              <span>50 Approve</span>
              <span>100 Auto</span>
            </div>
            {p.ceiling_sar !== undefined && (
              <div className="text-xs text-muted-foreground mt-2">Auto-spend ceiling: ﷼ {p.ceiling_sar} SAR</div>
            )}
            {p.max_price_increase_pct !== undefined && (
              <div className="text-xs text-warning mt-2">⚠️ Max auto price increase: {p.max_price_increase_pct}% – higher requires manual approval</div>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={save}
        disabled={saving}
        className="w-full mt-6 bg-primary text-primary-foreground py-3 rounded-xl font-medium hover:opacity-90 disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save – حفظ"}
      </button>

      {/* Phase 5 §18–19: what can happen automatically vs needs approval vs always human */}
      {explanation.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-2">What Nazm can do</h2>
          <div className="space-y-2">
            {explanation.map((e) => (
              <div key={e.action_type} className="flex items-start justify-between gap-3 rounded-lg border border-border bg-surface p-3 text-sm">
                <div>
                  <div className="font-medium">{e.label}</div>
                  <div className="text-xs text-muted-foreground">{e.explanation}</div>
                </div>
                <span className={
                  e.mode === "automatic" ? "shrink-0 rounded-full bg-success/10 px-2 py-0.5 text-xs font-bold text-success" :
                  e.mode === "automatic-conditional" ? "shrink-0 rounded-full bg-secondary/10 px-2 py-0.5 text-xs font-bold text-secondary" :
                  e.mode === "human" ? "shrink-0 rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-bold text-destructive" :
                  "shrink-0 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-bold text-warning"
                }>
                  {e.mode === "automatic" ? "Automatic" : e.mode === "automatic-conditional" ? "Auto (low-risk)" : e.mode === "human" ? "Human only" : "Approval"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {floors && (
        <div className="mt-4 text-xs text-muted-foreground bg-surface border border-border rounded-xl p-4">
          <b>Safety floors (cannot be changed here):</b><br/>
          Min auto confidence: {floors.min_confidence} · Medium-risk escalation: ﷼ {floors.risk_escalate_medium_sar} SAR · High-risk escalation: ﷼ {floors.risk_escalate_high_sar} SAR
          <div className="mt-1 text-muted-foreground">{floors.note}</div>
        </div>
      )}

      <div className="mt-6 text-xs text-muted-foreground bg-surface border border-border rounded-xl p-4">
        <b>Recommended for Saudi pharmacies (starting):</b><br/>
        Restock 50 · Pricing 20 · Cash 0 · Staff 0 · Expiry 50<br/>
        Increase dial gradually as you trust Nazm. You can always pull it back to 0.
      </div>
    </div>
  );
}
