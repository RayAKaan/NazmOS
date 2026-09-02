"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { logoMark } from "@/components/landing/logo";

/**
 * NazmakFooter — company-level footer.
 * Establishes Nazmak as parent, links NazmOS product + Free Audit.
 */
export function NazmakFooter() {
  const { t } = useI18n();
  const c = t.company.footer;

  return (
    <footer className="border-t border-border/70 bg-card/40">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-14 md:grid-cols-3 md:px-8">
        <div>
          <div className="flex items-center gap-3">
            <logoMark.Svg className="h-8 w-8" />
            <span className="font-serif text-lg font-medium text-foreground">Nazmak</span>
          </div>
          <p className="mt-4 max-w-xs text-sm text-muted-foreground">{c.tagline}</p>
        </div>

        <div>
          <span className="font-mono text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
            {t.company.nav.product}
          </span>
          <ul className="mt-4 space-y-2.5 text-sm">
            <li>
              <Link href="/products/nazmos" className="text-foreground hover:text-primary">
                {c.product}
                <span className="block text-xs text-muted-foreground">{c.productDesc}</span>
              </Link>
            </li>
            <li>
              <a href="#free-audit" className="text-foreground hover:text-primary">
                {c.freeAudit}
              </a>
            </li>
          </ul>
        </div>

        <div className="flex flex-col items-start gap-4 md:items-end">
          <p className="text-xs text-muted-foreground">{c.madeFor}</p>
          <div className="flex items-center gap-4">
            <Link href="/privacy" className="text-xs text-muted-foreground hover:text-foreground">
              {c.privacy}
            </Link>
            <Link href="/terms" className="text-xs text-muted-foreground hover:text-foreground">
              {c.terms}
            </Link>
          </div>
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} Nazmak. {c.rights}
          </p>
        </div>
      </div>
    </footer>
  );
}
