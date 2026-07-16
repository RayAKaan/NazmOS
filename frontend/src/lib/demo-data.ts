import type { AlertsResponse, DashboardSummary, SalesTrend } from "@/types/dashboard";

export const DEMO_SUMMARY: DashboardSummary = {
  today: {
    sales: 18450,
    transactions: 312,
    profit: 4620,
    avg_basket_size: 59.13,
  },
  this_month: {
    sales: 427800,
    transactions: 6810,
    profit: 98240,
  },
  comparison: {
    sales_change_percent: 18.4,
    profit_change_percent: 11.7,
    vs_last_month: true,
  },
  health_score: 86,
};

export const DEMO_ALERTS: AlertsResponse["alerts"] = [
  {
    id: "alert-1",
    type: "critical",
    icon: "alert-triangle",
    title: "Al-Qassim Sukari Dates running low",
    message: "Buraidah branch has 3.2 days of supply remaining.",
    detail: "Recommended transfer: 40 boxes from North Riyadh before weekend demand.",
    action_text: "Review transfer",
    action_type: "rebalance",
    item_id: "demo-dates-001",
    priority: 1,
    created_at: new Date().toISOString(),
  },
  {
    id: "alert-2",
    type: "warning",
    icon: "alert-circle",
    title: "Margin compression detected",
    message: "Almarai Fresh Cream margin dropped below 18% after supplier cost update.",
    detail: "Price shield recommendation is awaiting owner approval.",
    action_text: "Approve price shield",
    action_type: "pricing",
    item_id: "demo-cream-001",
    priority: 2,
    created_at: new Date().toISOString(),
  },
  {
    id: "alert-3",
    type: "info",
    icon: "info",
    title: "Recovery ledger preview ready",
    message: "Sales, stock, and margin movements have been refreshed for today’s sample order.",
    detail: "Sample preview only. Your real Money Audit uses your own sales and inventory data.",
    action_text: "View compliance preview",
    action_type: "compliance",
    item_id: null,
    priority: 3,
    created_at: new Date().toISOString(),
  },
];

const today = new Date();
export const DEMO_SALES_TREND: SalesTrend = {
  data: Array.from({ length: 14 }).map((_, idx) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (13 - idx));
    const weekendMultiplier = [4, 5, 6].includes(d.getDay()) ? 1.28 : 1;
    const sales = Math.round((10500 + idx * 420) * weekendMultiplier);
    return {
      date: d.toISOString().slice(0, 10),
      sales,
      profit: Math.round(sales * 0.24),
      transactions: Math.round(sales / 58),
    };
  }),
  summary: {
    avg_daily_sales: 13840,
    best_day: "Friday",
    worst_day: "Tuesday",
    trend_direction: "up",
  },
};

export const DEMO_INVENTORY = {
  items: [
    {
      item_id: "demo-dates-001",
      name: "Al-Qassim Sukari Dates 1kg",
      name_ar: "تمر سكري القصيم ١ كجم",
      sku: "DAT-SUK-01",
      category: "Dates / تمور",
      current_stock: 12,
      status: "critical",
    },
    {
      item_id: "demo-milk-001",
      name: "Fresh Milk 1L",
      name_ar: "حليب طازج ١ لتر",
      sku: "DAI-MILK-01",
      category: "Dairy / ألبان",
      current_stock: 38,
      status: "low",
    },
    {
      item_id: "demo-water-001",
      name: "Water 330ml Pack",
      name_ar: "مياه ٣٣٠ مل كرتون",
      sku: "BEV-WAT-24",
      category: "Beverages / مشروبات",
      current_stock: 180,
      status: "healthy",
    },
  ],
};

export const DEMO_SUPPLIERS = [
  {
    id: "supplier-1",
    name_ar: "مزارع تمور القصيم",
    name_en: "Al-Qassim Date Farms",
    city: "Buraidah",
    category: "dates_wholesale",
    phone: "+966500000101",
    whatsapp_number: "+966500000101",
    lead_time_days: 1,
    total_shops_ordering: 42,
    total_monthly_volume_sar: 185000,
  },
  {
    id: "supplier-2",
    name_ar: "مورد ألبان الرياض التجريبي",
    name_en: "Riyadh Demo Dairy Distributor",
    city: "Riyadh",
    category: "dairy",
    phone: "+966500000102",
    whatsapp_number: "+966500000102",
    lead_time_days: 2,
    total_shops_ordering: 118,
    total_monthly_volume_sar: 640000,
  },
];
