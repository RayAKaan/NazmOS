"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, Sparkles } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { logoMark } from "@/components/landing/logo";
import { track } from "@/lib/analytics";

export function SiteHeader() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const links: { href: string; label: string }[] = [
    { href: "#product", label: t.landing.nav.product },
    { href: "#how-it-works", label: t.landing.nav.howItWorks },
    { href: "#free-audit", label: t.landing.nav.freeAudit },
    { href: "#pricing", label: t.landing.nav.pricing },
    { href: "#faq", label: t.landing.nav.faq },
  ];

  const close = () => setOpen(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border/70 bg-background/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3 md:px-8">
        <Link
          href="/"
          onClick={close}
          className="flex items-center gap-3 rounded-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          aria-label={t.brand}
        >
          <logoMark.Svg className="h-9 w-9" />
          <div className="leading-tight">
            <span className="block font-serif text-xl font-black tracking-tight text-foreground">
              {t.brand}
            </span>
            <span className="block font-mono text-[9px] uppercase tracking-[0.28em] text-muted-foreground lowercase first-letter:uppercase">
              by Nazmak
            </span>
          </div>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-7 text-sm text-muted-foreground lg:flex">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="rounded-md px-1 py-1 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <LanguageSwitcher className="hidden sm:flex" />
          <Link
            href="/product-demo"
            className={cn(
              "hidden items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-semibold text-foreground transition-colors hover:bg-muted md:inline-flex"
            )}
          >
            <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
            {t.landing.nav.runDemo}
          </Link>
          <Link
            href="/register?intent=free-audit"
            onClick={() => track("nav.get_started", { pathname })}
            className="hidden items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-primary-foreground transition-colors hover:bg-primary/90 md:inline-flex"
          >
            {t.landing.nav.getStarted}
          </Link>

          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-foreground hover:bg-muted md:hidden"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {open && (
        <div className="border-t border-border/70 bg-background md:hidden">
          <nav aria-label="Mobile" className="mx-auto max-w-7xl space-y-1 px-5 py-4">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={close}
                className="block rounded-lg px-3 py-3 text-base font-medium text-foreground hover:bg-muted"
              >
                {l.label}
              </a>
            ))}
            <div className="flex items-center gap-2 pt-3">
              <LanguageSwitcher variant="compact" />
            </div>
            <Link
              href="/product-demo"
              onClick={close}
              className="mt-2 flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-3 text-sm font-semibold text-foreground"
            >
              <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
              {t.landing.nav.runDemo}
            </Link>
            <Link
              href="/register?intent=free-audit"
              onClick={close}
              className="mt-2 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-bold text-primary-foreground"
            >
              {t.landing.nav.getStarted}
            </Link>
          </nav>
        </div>
      )}
    </header>
  );
}
