"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

export function Footer() {
  const { t } = useI18n();

  const footerLinks = {
    [t.footer.product]: [
      { label: t.footer.features, href: "/features" },
      { label: t.footer.pricing, href: "/pricing" },
      { label: t.footer.integrations, href: "/integrations" },
      { label: t.footer.changelog, href: "/changelog" },
    ],
    [t.footer.company]: [
      { label: t.footer.about, href: "/about" },
      { label: t.footer.blog, href: "/blog" },
      { label: t.footer.careers, href: "/careers" },
      { label: t.footer.contact, href: "/contact" },
    ],
    [t.footer.resources]: [
      { label: t.footer.documentation, href: "/docs" },
      { label: t.footer.helpCenter, href: "/help" },
      { label: t.footer.apiReference, href: "/api-docs" },
      { label: t.footer.status, href: "/status" },
    ],
    [t.footer.legal]: [
      { label: t.footer.privacy, href: "/privacy" },
      { label: t.footer.terms, href: "/terms" },
      { label: t.footer.security, href: "/security" },
      { label: t.footer.gdpr, href: "/gdpr" },
    ],
  };

  return (
    <footer className="border-t border-border bg-secondary py-16 px-4">
      <div className="container mx-auto max-w-6xl">
        <div className="grid md:grid-cols-5 gap-12 mb-12">
          <div className="md:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <div className="w-10 h-10 bg-secondary border border-border flex items-center justify-center">
                <span className="text-foreground font-serif font-medium text-xl">ن</span>
              </div>
              <span className="font-medium text-xl text-foreground">NazmOS</span>
            </Link>
            <p className="text-muted-foreground text-sm">
              {t.footer.tagline}
            </p>
          </div>

          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h4 className="font-medium text-foreground mb-4">{category}</h4>
              <ul className="space-y-3">
                {links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="text-muted-foreground hover:text-foreground transition-colors text-sm"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="pt-8 border-t border-border flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-muted-foreground text-sm">
            © 2026 NazmOS. {t.footer.allRights}
          </p>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="w-2 h-2 bg-green-500 rounded-full" />
              {t.footer.systemsOperational}
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
