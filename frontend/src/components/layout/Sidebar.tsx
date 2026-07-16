"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Package, Upload, TrendingUp, Inbox, Truck, CalendarClock, Link2, Sparkles, Repeat2, Settings, WalletCards, ClipboardList } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

const AGENT_ENABLED = process.env.NEXT_PUBLIC_AGENT_ENABLED !== "false";
const PHARMACY_ENABLED = process.env.NEXT_PUBLIC_VERTICAL_PHARMACY !== "false";

export function Sidebar() {
  const pathname = usePathname();
  const { t, locale } = useI18n();
  const isAr = locale === "ar";

  const baseNavItems = [
    { href: "/feed", label: t.sidebar.feed, icon: Inbox, badge: AGENT_ENABLED ? "AI" : null },
    { href: "/dashboard", label: t.sidebar.dashboard, icon: LayoutDashboard },
    { href: "/money-audit", label: "Money Audit", icon: WalletCards, badge: "Free" },
    { href: "/orchestrator", label: t.sidebar.orchestrator || "Recovery Engine", icon: Sparkles, badge: "Recovery" },
    { href: "/inventory", label: t.sidebar.inventory, icon: Package },
    { href: "/forecast", label: t.sidebar.forecast, icon: TrendingUp },
    { href: "/upload", label: t.sidebar.upload, icon: Upload },
    { href: "/integrations", label: t.sidebar.integrations, icon: Link2, badge: "POS" },
    { href: "/recovery-match", label: t.sidebar.recoveryMatch || "Recovery Match", icon: Repeat2, badge: "Preview" },
    { href: "/ops", label: "Pilot Ops", icon: ClipboardList, badge: "Founder" },
  ];

  const toolsNavItems = [
    ...(PHARMACY_ENABLED ? [{ href: "/inventory/expiry", label: t.sidebar.expiry, icon: CalendarClock, badge: null }] : []),
    { href: "/suppliers", label: t.sidebar.suppliers, icon: Truck, badge: null },
  ];

  const renderItem = (item: any) => {
    const Icon = item.icon;
    const isActive = pathname === item.href;
    return (
      <Link
        key={item.href}
        href={item.href}
        className={cn(
          "flex items-center gap-3 px-4 py-3 rounded-xl transition-colors",
          isActive
            ? "bg-accent-blue/10 text-accent-blue border border-accent-blue/30"
            : "text-text-secondary hover:bg-surface-hover hover:text-text-primary"
        )}
      >
        <Icon className="w-5 h-5" />
        <span className="font-medium">{item.label}</span>
        {item.badge && (
          <span className={cn(
            "text-xs px-2 py-0.5 rounded ml-auto",
            item.badge === "AI" ? "bg-accent-purple/10 text-accent-purple" : "bg-surface-hover"
          )}>
            {item.badge}
          </span>
        )}
      </Link>
    );
  };

  return (
    <aside className="hidden md:flex flex-col w-60 border-r border-border bg-surface h-screen fixed left-0 top-0">
      <div className="p-5 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent-blue flex items-center justify-center">
            <span className="text-white font-bold text-xl font-serif">ن</span>
          </div>
          <div>
            <h1 className="font-bold text-lg">NazmOS</h1>
            <p className="text-xs text-text-muted">{isAr ? "نظام – الرياض" : "نظام – KSA"}</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
        {baseNavItems.map(renderItem)}
        
        {toolsNavItems.length > 0 && (
          <div className="pt-4 mt-4 border-t border-border space-y-2">
            <div className="px-4 text-xs text-text-muted uppercase tracking-wider">{t.sidebar.tools}</div>
            {toolsNavItems.map(renderItem)}
          </div>
        )}

        <div className="pt-4 mt-4 border-t border-border">
          <Link
            href="/settings/autonomy"
            className={cn(
              "flex items-center gap-3 px-4 py-3 rounded-xl transition-colors",
              pathname?.startsWith("/settings")
                ? "bg-accent-blue/10 text-accent-blue"
                : "text-text-secondary hover:bg-surface-hover hover:text-text-primary"
            )}
          >
            <Settings className="w-5 h-5" />
            <span className="font-medium">{t.sidebar.autonomy}</span>
            <span className="text-xs bg-surface-hover px-2 py-0.5 rounded ml-auto">نظم</span>
          </Link>
        </div>
      </nav>

      <div className="p-4 border-t border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-accent-purple/20 flex items-center justify-center">
            <span className="text-accent-purple font-medium">KSA</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium truncate">NazmOS KSA</p>
            <p className="text-xs text-text-muted">{isAr ? "الرياض • ر.س" : "Riyadh • SAR"}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
