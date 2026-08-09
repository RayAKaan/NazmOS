"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Eye,
  Flag,
  MapPin,
  PackageSearch,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  ToggleRight,
  XCircle,
} from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { FeatureGate } from "@/components/ui/FeatureGate";
import { cn } from "@/lib/utils";

type TabKey = "preview" | "listings" | "matches" | "completed" | "settings";

interface RecoveryOpportunity {
  item_id: string;
  item_name: string;
  sku?: string | null;
  barcode?: string | null;
  category?: string | null;
  current_stock: number;
  days_of_supply: number;
  estimated_surplus_qty: number;
  estimated_recovery_value_sar: number;
  status: string;
  next_step: string;
}

interface ListingRow {
  id: string;
  item_name: string;
  sku?: string | null;
  barcode?: string | null;
  category?: string | null;
  quantity_available: number;
  asking_price_sar: number;
  discount_pct?: number | null;
  expiry_date?: string | null;
  status: string;
  created_at?: string;
}

interface MatchRow {
  id: string;
  listing_id: string;
  buyer_business_id: string;
  buyer_item_id?: string | null;
  item_name?: string;
  sku?: string | null;
  asking_price_sar?: number;
  quantity_available?: number;
  match_score: number;
  distance_km?: number | null;
  buyer_need_qty?: number | null;
  buyer_days_left?: number | null;
  recovered_value_sar?: number | null;
  status: string;
  created_at?: string;
}

interface SettingsState {
  is_enabled?: boolean;
  allow_contact_reveal?: boolean;
  max_distance_km?: number;
}

const sample: RecoveryOpportunity[] = [
  {
    item_id: "sample-coffee",
    item_name: "Coffee Beans 250g",
    sku: "COF-250",
    barcode: "628000000001",
    category: "Packaged goods",
    current_stock: 68,
    days_of_supply: 64,
    estimated_surplus_qty: 40,
    estimated_recovery_value_sar: 1440,
    status: "sample_preview",
    next_step: "A nearby store may need this stock before buying from a distributor.",
  },
  {
    item_id: "sample-dates",
    item_name: "Sukari Dates 1kg",
    sku: "DAT-SUK-01",
    barcode: "628000000002",
    category: "Dates",
    current_stock: 120,
    days_of_supply: 48,
    estimated_surplus_qty: 55,
    estimated_recovery_value_sar: 3850,
    status: "sample_preview",
    next_step: "Healthy surplus stock can become recovered cash through opted-in nearby stores.",
  },
];

const tabs: { key: TabKey; label: string }[] = [
  { key: "preview", label: "Preview" },
  { key: "listings", label: "My Listings" },
  { key: "matches", label: "Matches" },
  { key: "completed", label: "Completed" },
  { key: "settings", label: "Settings" },
];

const pilotRules = [
  ["Both sides approve", "No contact reveal until buyer and seller both show intent."],
  ["Founder-review mindset", "Treat every early match as manual ops learning, not full automation."],
  ["Safe categories only", "No expired, near-expiry, cold-chain, medicine, baby formula, frozen, meat, or cosmetics."],
  ["No marketplace liability", "No escrow, no payment handling, no delivery promise inside NazmOS v1."],
] as const;

function money(v: number | string | null | undefined) {
  return `SAR ${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    seller_approved: "bg-brand-amber/10 text-brand-amber",
    suggested: "bg-brand-amber/10 text-brand-amber",
    seller_interested: "bg-blue-500/10 text-blue-300",
    buyer_interested: "bg-blue-500/10 text-blue-300",
    mutual_match: "bg-whatsapp/10 text-whatsapp-faint",
    contact_revealed: "bg-brand-green/10 text-brand-green",
    completed: "bg-brand-green/10 text-brand-green",
    rejected: "bg-white/10 text-white/50",
    issue_reported: "bg-brand-red/10 text-brand-red-light",
  };
  return <span className={cn("rounded-full px-3 py-1 text-xs font-bold", styles[status] || "bg-white/10 text-white/60")}>{status.replaceAll("_", " ")}</span>;
}

export default function RecoveryMatchPage() {
  const { businessId } = useAppStore();
  const [activeTab, setActiveTab] = useState<TabKey>("preview");
  const [opportunities, setOpportunities] = useState<RecoveryOpportunity[]>([]);
  const [listings, setListings] = useState<ListingRow[]>([]);
  const [buyerMatches, setBuyerMatches] = useState<MatchRow[]>([]);
  const [sellerMatches, setSellerMatches] = useState<MatchRow[]>([]);
  const [settings, setSettings] = useState<SettingsState | null>(null);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [contactInfo, setContactInfo] = useState<any | null>(null);

  const [selected, setSelected] = useState<RecoveryOpportunity | null>(null);
  const [expiryDate, setExpiryDate] = useState("");
  const [quantity, setQuantity] = useState("");
  const [discount, setDiscount] = useState("20");

  const [recoveredValues, setRecoveredValues] = useState<Record<string, string>>({});
  const [issueMatch, setIssueMatch] = useState<MatchRow | null>(null);
  const [issueType, setIssueType] = useState("other");
  const [issueNotes, setIssueNotes] = useState("");
  const [maxDistance, setMaxDistance] = useState("5");
  const [allowReveal, setAllowReveal] = useState(false);
  const [activating, setActivating] = useState(false);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    try {
      const [previewRes, settingsRes, listingsRes, buyerRes, sellerRes] = await Promise.all([
        api.get(`/recovery-match/preview?business_id=${businessId}`),
        api.get(`/recovery-match/settings?business_id=${businessId}`).catch(() => ({ data: null })),
        api.get(`/recovery-match/listings?business_id=${businessId}`).catch(() => ({ data: { listings: [] } })),
        api.get(`/recovery-match/matches?business_id=${businessId}&role=buyer`).catch(() => ({ data: { matches: [] } })),
        api.get(`/recovery-match/matches?business_id=${businessId}&role=seller`).catch(() => ({ data: { matches: [] } })),
      ]);
      setOpportunities(previewRes.data.opportunities || []);
      setSettings(settingsRes.data);
      setAllowReveal(Boolean(settingsRes.data?.allow_contact_reveal));
      setMaxDistance(String(settingsRes.data?.max_distance_km || 5));
      setListings(listingsRes.data.listings || []);
      setBuyerMatches(buyerRes.data.matches || []);
      setSellerMatches(sellerRes.data.matches || []);
      setLocked(false);
    } catch (err: any) {
      if (err?.response?.status === 402) setLocked(true);
      setOpportunities([]);
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    load();
  }, [load]);

  const enableRecoveryMatch = async () => {
    if (!businessId) return;
    setNotice(null);
    try {
      const res = await api.put("/recovery-match/settings", {
        business_id: businessId,
        is_enabled: true,
        allow_contact_reveal: allowReveal,
        max_distance_km: Number(maxDistance || 5),
      });
      setSettings(res.data);
      setNotice("Recovery Match settings saved.");
      setLocked(false);
      await load();
    } catch (err: any) {
      if (err?.response?.status === 402) setLocked(true);
      setNotice(err?.response?.data?.detail?.message || "Recovery Match requires Growing Retail.");
    }
  };

  const activateRecoveryMatch = async () => {
    if (!businessId) return;
    setActivating(true);
    setNotice(null);
    try {
      await api.post("/recovery-match/activate", {
        business_id: businessId,
        auto_create_listings: false,
        max_listings: 3,
      });
      setNotice("Recovery Match activated.");
      setLocked(false);
      await load();
    } catch (err: any) {
      if (err?.response?.status === 402) setLocked(true);
      setNotice(err?.response?.data?.detail || "Activation requires Growing Retail.");
    } finally {
      setActivating(false);
    }
  };

  const openListingForm = (opp: RecoveryOpportunity) => {
    setSelected(opp);
    setExpiryDate("");
    setQuantity(String(Math.round(opp.estimated_surplus_qty || 1)));
    setDiscount("20");
    setNotice(null);
  };

  const createListing = async () => {
    if (!businessId || !selected) return;
    try {
      await api.post("/recovery-match/listings", {
        business_id: businessId,
        item_id: selected.item_id,
        quantity_available: Number(quantity),
        discount_pct: Number(discount),
        expiry_date: expiryDate,
        listing_days: 7,
        notes: "Created from Recovery Match preview",
      });
      setSelected(null);
      setNotice("Listing created. Open My Listings to suggest nearby buyers.");
      setActiveTab("listings");
      await load();
    } catch (err: any) {
      if (err?.response?.status === 402) setLocked(true);
      setNotice(err?.response?.data?.detail || "Could not create listing. Check expiry date and paid feature access.");
    }
  };

  const suggestMatches = async (listingId: string) => {
    if (!businessId) return;
    setNotice(null);
    try {
      const res = await api.post(`/recovery-match/listings/${listingId}/suggest-matches?business_id=${businessId}`);
      setNotice(`Suggested ${res.data.count || 0} buyer matches.`);
      await load();
      setActiveTab("matches");
    } catch (err: any) {
      setNotice(err?.response?.data?.detail || "Could not suggest matches yet.");
    }
  };

  const buyerInterested = async (matchId: string) => {
    if (!businessId) return;
    await api.post(`/recovery-match/matches/${matchId}/buyer-interest`, { business_id: businessId });
    setNotice("Interest recorded. If seller already approved, this becomes a mutual match.");
    await load();
  };

  const rejectMatch = async (matchId: string) => {
    if (!businessId) return;
    await api.post(`/recovery-match/matches/${matchId}/reject`, { business_id: businessId, notes: "Rejected from dashboard" });
    setNotice("Match rejected.");
    await load();
  };

  const revealContact = async (matchId: string) => {
    if (!businessId) return;
    try {
      const res = await api.post(`/recovery-match/matches/${matchId}/reveal-contact`, { business_id: businessId });
      setContactInfo(res.data);
      setNotice("Contact details revealed. Payment, pickup, and inspection remain between merchants.");
      await load();
    } catch (err: any) {
      setNotice(err?.response?.data?.detail || "Contact can be revealed only after both sides approve.");
    }
  };

  const completeMatch = async (matchId: string) => {
    if (!businessId) return;
    const recovered = recoveredValues[matchId];
    if (!recovered) {
      setNotice("Enter recovered value before marking completed.");
      return;
    }
    await api.post(`/recovery-match/matches/${matchId}/complete`, { business_id: businessId, recovered_value_sar: Number(recovered) });
    setNotice("Match marked completed and recovered value recorded.");
    await load();
    setActiveTab("completed");
  };

  const reportIssue = async () => {
    if (!businessId || !issueMatch) return;
    await api.post(`/recovery-match/matches/${issueMatch.id}/report-issue`, {
      business_id: businessId,
      issue_type: issueType,
      notes: issueNotes,
    });
    setIssueMatch(null);
    setIssueNotes("");
    setIssueType("other");
    setNotice("Issue reported for founder review.");
    await load();
  };

  const previewRows = opportunities.length ? opportunities : sample;
  const allMatches = [...buyerMatches.map((m) => ({ ...m, role: "buyer" })), ...sellerMatches.map((m) => ({ ...m, role: "seller" }))];
  const completed = allMatches.filter((m) => m.status === "completed");

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-3xl border border-white/10 bg-brand-night p-6 text-white shadow-2xl shadow-black/20 md:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-brand-amber/30 bg-brand-amber/10 px-3 py-2 text-xs font-bold uppercase tracking-[0.22em] text-brand-amber">
              <Sparkles className="h-4 w-4" /> Manual-confirm pilot
            </div>
            <h1 className="mt-5 max-w-4xl font-serif text-4xl font-black leading-tight tracking-[-0.03em] md:text-6xl">
              Recovery Match turns healthy surplus stock into recovered cash.
            </h1>
            <p className="mt-4 max-w-3xl leading-7 text-white/62">
              Match surplus items with nearby opted-in stores — no payments, no escrow, no delivery, and no risky categories in v1.
            </p>
          </div>
          <button onClick={load} className="inline-flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm font-bold text-white/70 hover:bg-white/5">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-4">
        {pilotRules.map(([title, body], index) => (
          <div key={title} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-brand-amber">Rule {index + 1}</p>
            <h3 className="mt-2 font-bold text-white">{title}</h3>
            <p className="mt-1 text-sm leading-6 text-text-secondary">{body}</p>
          </div>
        ))}
      </section>

      {locked && (
        <FeatureGate
          feature="recovery_match"
          title="Recovery Match is part of Growing Retail"
          description="Free users see preview opportunities. Paid plans unlock listings, buyer interest, contact reveal, and completion tracking."
          requiredPlan="Growing Retail"
        />
      )}

      {notice && <div className="rounded-2xl border border-brand-amber/30 bg-brand-amber/10 p-4 text-sm text-brand-amber">{notice}</div>}

      <div className="flex gap-2 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.03] p-2">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "whitespace-nowrap rounded-xl px-4 py-2 text-sm font-bold transition",
              activeTab === tab.key ? "bg-brand-amber text-black" : "text-white/60 hover:bg-white/5 hover:text-white"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "settings" && (
        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="text-2xl font-bold">Recovery Match Settings</h2>
          <p className="mt-1 text-sm text-text-secondary">Opt-in is required. Contact reveal remains manual and permissioned.</p>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <label className="space-y-2 text-sm">
              <span className="text-text-secondary">Max distance km</span>
              <input value={maxDistance} onChange={(e) => setMaxDistance(e.target.value)} className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white" />
            </label>
            <label className="flex items-end gap-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm">
              <input type="checkbox" checked={allowReveal} onChange={(e) => setAllowReveal(e.target.checked)} />
              <span>Allow contact reveal after mutual approval</span>
            </label>
            <div className="flex items-end gap-2">
              <button onClick={enableRecoveryMatch} className="rounded-xl bg-brand-amber px-4 py-2 text-sm font-bold text-black">
                {settings?.is_enabled ? "Save Settings" : "Enable Recovery Match"}
              </button>
              <button
                onClick={activateRecoveryMatch}
                disabled={activating || settings?.is_enabled}
                className="rounded-xl bg-brand-green px-4 py-2 text-sm font-bold text-black disabled:opacity-50"
              >
                {activating ? "Activating…" : "Activate"}
              </button>
            </div>
          </div>
        </section>
      )}

      {activeTab === "preview" && (
        <section className="rounded-3xl border border-border bg-surface p-6">
          <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-bold">Recovery Match Preview</h2>
              <p className="mt-1 text-sm text-text-secondary">{loading ? "Scanning surplus candidates..." : "Preview opportunities. Create a listing only after confirming expiry and quantity."}</p>
            </div>
            <div className="inline-flex items-center gap-2 rounded-full bg-brand-red/10 px-3 py-2 text-xs font-bold text-brand-red-light">
              <ShieldAlert className="h-4 w-4" /> Regulated/near-expiry categories excluded
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {previewRows.map((row: any) => (
              <div key={`${row.item_name}-${row.sku}`} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-bold text-white">{row.item_name}</h3>
                    <p className="mt-1 text-xs text-text-muted">SKU: {row.sku || "—"} · Barcode: {row.barcode || "—"} · {row.category || "Uncategorized"}</p>
                  </div>
                  <StatusBadge status={row.status || "preview"} />
                </div>
                <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                  <Info label="Current stock" value={Number(row.current_stock).toLocaleString()} />
                  <Info label="Days supply" value={String(row.days_of_supply)} />
                  <Info label="Surplus qty" value={String(row.estimated_surplus_qty)} />
                  <Info label="Potential recovery" value={money(row.estimated_recovery_value_sar)} good />
                </div>
                <p className="mt-4 text-sm leading-6 text-text-secondary">{row.next_step}</p>
                <button onClick={() => openListingForm(row)} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-amber px-4 py-2 text-sm font-bold text-black">
                  Offer Stock <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "listings" && (
        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="text-2xl font-bold">My Listings</h2>
          <p className="mt-1 text-sm text-text-secondary">Seller-approved surplus stock. Suggest matches after creating a listing.</p>
          <div className="mt-5 grid gap-4">
            {listings.length === 0 && <Empty text="No real listings yet. Create one from Preview." />}
            {listings.map((listing) => (
              <div key={listing.id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-white">{listing.item_name}</h3>
                    <p className="mt-1 text-xs text-text-muted">SKU: {listing.sku || "—"} · Expiry: {listing.expiry_date || "—"}</p>
                  </div>
                  <StatusBadge status={listing.status} />
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-4">
                  <Info label="Qty" value={String(listing.quantity_available)} />
                  <Info label="Asking price" value={money(listing.asking_price_sar)} good />
                  <Info label="Discount" value={`${listing.discount_pct || 0}%`} />
                  <Info label="Created" value={listing.created_at?.slice(0, 10) || "—"} />
                </div>
                <button onClick={() => suggestMatches(listing.id)} className="mt-5 rounded-xl bg-brand-amber px-4 py-2 text-sm font-bold text-black">
                  Suggest Nearby Buyers
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === "matches" && (
        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="text-2xl font-bold">Incoming & Seller Matches</h2>
          <p className="mt-1 text-sm text-text-secondary">Buyer interest, seller suggestions, mutual matches, and contact reveal.</p>
          <div className="mt-5 grid gap-4">
            {allMatches.filter((m) => m.status !== "completed").length === 0 && <Empty text="No matches yet. Create a listing and suggest nearby buyers." />}
            {allMatches.filter((m) => m.status !== "completed").map((match) => (
              <MatchCard
                key={`${match.role}-${match.id}`}
                match={match}
                role={match.role as string}
                recoveredValue={recoveredValues[match.id] || ""}
                onRecoveredValue={(value) => setRecoveredValues((prev) => ({ ...prev, [match.id]: value }))}
                onBuyerInterest={() => buyerInterested(match.id)}
                onReject={() => rejectMatch(match.id)}
                onReveal={() => revealContact(match.id)}
                onComplete={() => completeMatch(match.id)}
                onReport={() => setIssueMatch(match)}
              />
            ))}
          </div>
        </section>
      )}

      {activeTab === "completed" && (
        <section className="rounded-3xl border border-border bg-surface p-6">
          <h2 className="text-2xl font-bold">Completed Recovery</h2>
          <p className="mt-1 text-sm text-text-secondary">Recovered value from completed manual-confirm matches.</p>
          <div className="mt-5 grid gap-4">
            {completed.length === 0 && <Empty text="No completed matches yet." />}
            {completed.map((match) => (
              <div key={`${match.role}-${match.id}`} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-bold text-white">{match.item_name || "Recovery Match"}</h3>
                    <p className="mt-1 text-sm text-text-secondary">Recovered value: <span className="font-bold text-brand-green">{money(match.recovered_value_sar)}</span></p>
                  </div>
                  <StatusBadge status={match.status} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {selected && (
        <section className="rounded-3xl border border-brand-amber/30 bg-brand-amber/10 p-6">
          <h2 className="text-xl font-bold text-white">Create seller listing: {selected.item_name}</h2>
          <p className="mt-2 text-sm text-text-secondary">Real listings require expiry date and manual confirmation. Risky categories are blocked.</p>
          <div className="mt-5 grid gap-4 md:grid-cols-4">
            <Field label="Quantity available" value={quantity} setValue={setQuantity} />
            <Field label="Discount %" value={discount} setValue={setDiscount} />
            <label className="space-y-2 text-sm">
              <span className="text-text-secondary">Expiry date</span>
              <input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white" />
            </label>
            <div className="flex items-end gap-2">
              <button onClick={createListing} className="rounded-xl bg-brand-green px-4 py-2 text-sm font-bold text-black">Create Listing</button>
              <button onClick={() => setSelected(null)} className="rounded-xl border border-white/10 px-4 py-2 text-sm font-bold text-white">Cancel</button>
            </div>
          </div>
        </section>
      )}

      {contactInfo && (
        <section className="rounded-3xl border border-whatsapp/30 bg-whatsapp/10 p-6">
          <h2 className="text-xl font-bold text-white">Contact Revealed</h2>
          <p className="mt-2 text-sm text-text-secondary">Payment, pickup, and inspection are handled directly between merchants.</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Info label="Seller" value={`${contactInfo.seller?.name || "—"} · ${contactInfo.seller?.phone || "—"}`} />
            <Info label="Buyer" value={`${contactInfo.buyer?.name || "—"} · ${contactInfo.buyer?.phone || "—"}`} />
          </div>
        </section>
      )}

      {issueMatch && (
        <section className="rounded-3xl border border-brand-red/30 bg-brand-red/10 p-6">
          <h2 className="text-xl font-bold text-white">Report Issue</h2>
          <p className="mt-2 text-sm text-text-secondary">This flags the match for founder review.</p>
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            <label className="space-y-2 text-sm">
              <span className="text-text-secondary">Issue type</span>
              <select value={issueType} onChange={(e) => setIssueType(e.target.value)} className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white">
                <option value="wrong_quantity">Wrong quantity</option>
                <option value="wrong_condition">Wrong condition</option>
                <option value="near_expiry">Near expiry</option>
                <option value="no_show">No show</option>
                <option value="other">Other</option>
              </select>
            </label>
            <Field label="Notes" value={issueNotes} setValue={setIssueNotes} />
            <div className="flex items-end gap-2">
              <button onClick={reportIssue} className="rounded-xl bg-brand-red px-4 py-2 text-sm font-bold text-white">Submit Issue</button>
              <button onClick={() => setIssueMatch(null)} className="rounded-xl border border-white/10 px-4 py-2 text-sm font-bold text-white">Cancel</button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function Info({ label, value, good = false }: { label: string; value: string; good?: boolean }) {
  return <div className="rounded-xl bg-black/20 p-3"><p className="text-text-muted">{label}</p><p className={cn("mt-1 font-bold text-white", good && "text-brand-green")}>{value}</p></div>;
}

function Field({ label, value, setValue }: { label: string; value: string; setValue: (value: string) => void }) {
  return <label className="space-y-2 text-sm"><span className="text-text-secondary">{label}</span><input value={value} onChange={(e) => setValue(e.target.value)} className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white" /></label>;
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-2xl border border-dashed border-white/10 p-8 text-center text-sm text-text-muted">{text}</div>;
}

function MatchCard({
  match,
  role,
  recoveredValue,
  onRecoveredValue,
  onBuyerInterest,
  onReject,
  onReveal,
  onComplete,
  onReport,
}: {
  match: MatchRow & { role?: string };
  role: string;
  recoveredValue: string;
  onRecoveredValue: (value: string) => void;
  onBuyerInterest: () => void;
  onReject: () => void;
  onReveal: () => void;
  onComplete: () => void;
  onReport: () => void;
}) {
  const canBuyerAccept = role === "buyer" && ["suggested", "seller_interested"].includes(match.status);
  const canReveal = ["mutual_match"].includes(match.status);
  const canComplete = ["contact_revealed"].includes(match.status);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-lg font-bold text-white">{match.item_name || "Recovery Match"}</h3>
          <p className="mt-1 text-xs text-text-muted">Role: {role} · Score: {Number(match.match_score || 0).toFixed(0)} · Distance: {match.distance_km ?? "—"} km</p>
        </div>
        <StatusBadge status={match.status} />
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <Info label="Qty" value={String(match.quantity_available || match.buyer_need_qty || "—")} />
        <Info label="Price" value={money(match.asking_price_sar)} good />
        <Info label="Buyer days left" value={String(match.buyer_days_left ?? "—")} />
        <Info label="Recovered" value={money(match.recovered_value_sar)} good />
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {canBuyerAccept && <button onClick={onBuyerInterest} className="rounded-xl bg-whatsapp px-4 py-2 text-sm font-bold text-black">Interested</button>}
        {canReveal && <button onClick={onReveal} className="rounded-xl bg-brand-amber px-4 py-2 text-sm font-bold text-black">Reveal Contact</button>}
        {canComplete && <><input placeholder="Recovered SAR" value={recoveredValue} onChange={(e) => onRecoveredValue(e.target.value)} className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-white" /><button onClick={onComplete} className="rounded-xl bg-brand-green px-4 py-2 text-sm font-bold text-black">Mark Completed</button></>}
        {!match.status.includes("rejected") && match.status !== "completed" && <button onClick={onReject} className="rounded-xl border border-white/10 px-4 py-2 text-sm font-bold text-white/70">Reject</button>}
        <button onClick={onReport} className="rounded-xl border border-brand-red/30 px-4 py-2 text-sm font-bold text-brand-red-light">Report Issue</button>
      </div>
    </div>
  );
}
