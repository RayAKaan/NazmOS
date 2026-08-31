"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { logoMark } from "@/components/landing/logo";

export function SiteFooter() {
  const { t } = useI18n();

  return (
    <footer className="border-t border-border px-5 py-12 md:px-8">
      <div className="mx-auto flex max-w-7xl flex-col justify-between gap-8 md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <logoMark.Svg className="h-10 w-10" />
          <div>
            <p className="font-serif text-2xl font-black text-foreground">{t.brand}</p>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">{t.landing.footer.tagline}</p>
          </div>
        </div>

        <div className="flex flex-col items-start gap-4 md:items-end">
          <div className="flex flex-wrap items-center gap-5 text-sm">
            <Link href="/privacy" className="font-semibold text-muted-foreground hover:text-foreground">
              {t.landing.footer.privacy}
            </Link>
            <Link href="/terms" className="font-semibold text-muted-foreground hover:text-foreground">
              {t.landing.footer.terms}
            </Link>
            <Link href="/register?intent=free-audit" className="font-bold text-primary hover:underline">
              {t.landing.nav.getStarted}
            </Link>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-success" aria-hidden="true" />
              {t.landing.footer.systemsOperational}
            </span>
            <span>{t.landing.footer.madeIn}</span>
          </div>
        </div>
      </div>

      <div className="mx-auto mt-10 flex max-w-7xl flex-col gap-2 border-t border-border pt-6 text-xs text-muted-foreground/70 sm:flex-row sm:justify-between">
        <p>© {new Date().getFullYear()} Nazmak. {t.landing.footer.allRights}</p>
        <p>{t.landing.nav.signedOut}</p>
      </div>
    </footer>
  );
}
