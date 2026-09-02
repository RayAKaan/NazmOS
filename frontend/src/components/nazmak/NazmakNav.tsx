"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Menu, X, ChevronDown } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { logoMark } from "@/components/landing/logo";
import { track } from "@/lib/analytics";

/**
 * NazmakNav — the company navigation.
 *
 * Establishes brand hierarchy: NAZMAK (company) → Products ▸ NazmOS.
 * Primary conversion: Free Audit. Language + theme toggles.
 * Mobile collapses to a hamburger with the same structure.
 */
export function NazmakNav() {
  const { t, dir } = useI18n();
  const [open, setOpen] = useState(false);
  const [prodOpen, setProdOpen] = useState(false);
  const prodRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (prodRef.current && !prodRef.current.contains(e.target as Node)) {
        setProdOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const close = () => setOpen(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border/70 bg-background/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3 md:px-8">
        {/* Brand */}
        <Link
          href="/"
          onClick={close}
          className="flex items-center gap-3 rounded-md focus-ring"
          aria-label="Nazmak"
        >
          <logoMark.Svg className="h-8 w-8" />
          <span className="font-serif text-xl font-medium tracking-tight text-foreground">
            Nazmak
          </span>
        </Link>

        {/* Desktop nav */}
        <nav aria-label="Primary" className="hidden items-center gap-2 text-sm lg:flex">
          <div ref={prodRef} className="relative">
            <button
              type="button"
              onClick={() => setProdOpen((v) => !v)}
              aria-expanded={prodOpen}
              className={cn(
                "flex items-center gap-1 rounded-md px-3 py-2 font-medium text-muted-foreground transition-colors hover:text-foreground focus-ring",
                prodOpen && "text-foreground"
              )}
            >
              {t.company.nav.product}
              <ChevronDown className={cn("h-4 w-4 transition-transform", prodOpen && "rotate-180")} aria-hidden="true" />
            </button>
            {prodOpen && (
              <div className="absolute start-0 top-full mt-2 w-64 overflow-hidden rounded-xl border border-border bg-card p-2 shadow-elevation-3">
                <Link
                  href="/products/nazmos"
                  onClick={() => {
                    setProdOpen(false);
                    track("nav.products.nazmos", { pathname: "/" });
                  }}
                  className="flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-muted"
                >
                  <span className="mt-0.5 h-8 w-8 shrink-0 rounded-lg bg-primary/10 p-2">
                    <span className="block h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
                  </span>
                  <span>
                    <span className="block font-semibold text-foreground">{t.company.nav.products.nazmos}</span>
                    <span className="block text-xs text-muted-foreground">{t.company.nav.products.nazmosDesc}</span>
                  </span>
                </Link>
              </div>
            )}
          </div>

          <Link
            href="#principles"
            className="rounded-md px-3 py-2 font-medium text-muted-foreground transition-colors hover:text-foreground focus-ring"
          >
            {t.company.nav.company}
          </Link>
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <LanguageSwitcher className="hidden sm:flex" />
          <Link
            href="#free-audit"
            onClick={close}
            className="hidden rounded-lg border border-border px-3 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-muted md:inline-flex"
          >
            {t.company.nav.freeAudit}
          </Link>
          <Link
            href="/register?intent=free-audit"
            onClick={() => track("nav.get_started", { pathname: "/" })}
            className="hidden items-center rounded-lg bg-primary px-4 py-2 text-sm font-bold text-primary-foreground transition-colors hover:bg-primary/90 md:inline-flex"
          >
            {t.company.nav.getStarted}
          </Link>

          {/* Mobile hamburger */}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-foreground hover:bg-muted lg:hidden"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="border-t border-border/70 bg-background lg:hidden">
          <nav aria-label="Mobile" className="mx-auto max-w-7xl space-y-1 px-5 py-4">
            <Link
              href="/products/nazmos"
              onClick={close}
              className="block rounded-lg px-3 py-3 text-base font-semibold text-foreground hover:bg-muted"
            >
              {t.company.nav.products.nazmos}
              <span className="block text-xs font-normal text-muted-foreground">{t.company.nav.products.nazmosDesc}</span>
            </Link>
            <a
              href="#free-audit"
              onClick={close}
              className="block rounded-lg px-3 py-3 text-base font-medium text-foreground hover:bg-muted"
            >
              {t.company.nav.freeAudit}
            </a>
            <a
              href="#principles"
              onClick={close}
              className="block rounded-lg px-3 py-3 text-base font-medium text-foreground hover:bg-muted"
            >
              {t.company.nav.company}
            </a>
            <div className="flex items-center gap-2 pt-3">
              <LanguageSwitcher variant="compact" />
            </div>
            <Link
              href="/register?intent=free-audit"
              onClick={close}
              className="mt-2 flex items-center justify-center rounded-lg bg-primary px-4 py-3 text-sm font-bold text-primary-foreground"
            >
              {t.company.nav.getStarted}
            </Link>
          </nav>
        </div>
      )}
    </header>
  );
}
