"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarClock,
  ClipboardList,
  Inbox,
  LayoutDashboard,
  Link2,
  MoreHorizontal,
  Package,
  Repeat2,
  Settings,
  Sparkles,
  TrendingUp,
  Truck,
  Upload,
  WalletCards,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

const AGENT_ENABLED = process.env.NEXT_PUBLIC_AGENT_ENABLED !== "false";
const PHARMACY_ENABLED = process.env.NEXT_PUBLIC_VERTICAL_PHARMACY !== "false";

export function MobileNav() {
  const pathname = usePathname();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  const primaryNav = [
    { href: "/dashboard", label: t.sidebar.dashboard, icon: LayoutDashboard },
    { href: "/money-audit", label: "Money Audit", icon: WalletCards },
    { href: "/upload", label: t.sidebar.upload, icon: Upload },
    { href: "/inventory", label: t.sidebar.inventory, icon: Package },
    { href: "/recovery-match", label: t.sidebar.recoveryMatch || "Recovery Match", icon: Repeat2 },
  ];

  const moreNav = [
    { href: "/feed", label: t.sidebar.feed, icon: Inbox },
    { href: "/chat", label: t.sidebar.copilot || "Nazm Copilot", icon: Sparkles },
    { href: "/orchestrator", label: t.sidebar.orchestrator || "Recovery Engine", icon: Sparkles },
    { href: "/forecast", label: t.sidebar.forecast, icon: TrendingUp },
    { href: "/integrations", label: t.sidebar.integrations, icon: Link2 },
    { href: "/ops", label: "Pilot Ops", icon: ClipboardList },
    ...(PHARMACY_ENABLED
      ? [{ href: "/inventory/expiry", label: t.sidebar.expiry, icon: CalendarClock }]
      : []),
    { href: "/suppliers", label: t.sidebar.suppliers, icon: Truck },
    { href: "/settings/autonomy", label: t.sidebar.autonomy, icon: Settings },
  ];

  const isActive = (href: string) => (href === "/settings/autonomy" ? pathname?.startsWith("/settings") : pathname === href);

  return (
    <>
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-card border-t border-border z-50">
        <div className="flex items-center justify-around py-2">
          {primaryNav.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-label={item.label}
                className={cn(
                  "flex flex-col items-center gap-1 px-3 py-2 min-w-[64px]",
                  isActive(item.href) ? "text-primary" : "text-muted-foreground"
                )}
              >
                <Icon className="w-5 h-5" />
                <span className="text-xs font-medium">{item.label}</span>
              </Link>
            );
          })}
          <button
            onClick={() => setOpen(true)}
            aria-label={t.sidebar.more}
            aria-expanded={open}
            className={cn(
              "flex flex-col items-center gap-1 px-3 py-2 min-w-[64px]",
              open ? "text-primary" : "text-muted-foreground"
            )}
          >
            <MoreHorizontal className="w-5 h-5" />
            <span className="text-xs font-medium">{t.sidebar.more}</span>
          </button>
        </div>
      </nav>

      {open && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-overlay" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute inset-x-0 bottom-0 bg-card border-t border-border rounded-t-3xl max-h-[80vh] overflow-y-auto pb-6">
            <div className="sticky top-0 bg-card flex items-center justify-between px-5 py-4 border-b border-border">
              <p className="font-semibold">{t.sidebar.allTools}</p>
              <button onClick={() => setOpen(false)} aria-label={t.sidebar.close}>
                <X className="w-5 h-5 text-muted-foreground" />
              </button>
            </div>
            <nav className="p-3 space-y-1">
              {moreNav.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 rounded-xl transition-colors",
                      isActive(item.href)
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-card-hover hover:text-foreground"
                    )}
                  >
                    <Icon className="w-5 h-5" />
                    <span className="font-medium">{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
