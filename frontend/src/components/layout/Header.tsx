'use client';

import * as React from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Menu, X, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useI18n } from '@/lib/i18n';
import { LanguageSwitcher } from '@/components/ui/LanguageSwitcher';

// Dashboard top bar. The landing page ships its own inline nav (src/app/page.tsx);
// this header is used only inside the authenticated (dashboard) layout, so it
// points at real dashboard destinations rather than marketing routes.
const DEMO_HREF = '/product-demo';

export function Header() {
  const [isScrolled, setIsScrolled] = React.useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
  const { t } = useI18n();

  React.useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <>
      <header
        className={cn(
          'fixed top-0 left-0 right-0 z-50 transition-all duration-300',
          isScrolled
            ? 'bg-bg-primary/95 backdrop-blur-lg border-b border-border-primary'
            : 'bg-transparent'
        )}
      >
        <div className="container mx-auto px-6">
          <div className="flex items-center justify-between h-16">
            <Link href="/dashboard" className="flex items-center gap-3" aria-label="NazmOS dashboard">
              <div className="w-8 h-8 bg-bg-secondary border border-border-primary flex items-center justify-center">
                <span className="font-serif text-lg text-accent-primary">ن</span>
              </div>
              <span className="font-serif text-lg text-text-primary tracking-tight">NAZMOS</span>
            </Link>

            <nav className="hidden lg:flex items-center gap-8">
              <Link
                href={DEMO_HREF}
                className="font-sans text-sm flex items-center gap-1 transition-colors duration-200 text-text-secondary hover:text-text-primary"
              >
                <Sparkles className="w-3 h-3" />
                {t.header.demo}
              </Link>
            </nav>

            <div className="hidden lg:flex items-center gap-4">
              <LanguageSwitcher variant="compact" />
              <Link href="/upload">
                <Button size="sm">{t.header.startFree}</Button>
              </Link>
            </div>

            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="lg:hidden p-2 text-text-secondary hover:text-text-primary transition-colors"
              aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
            >
              {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </header>

      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden bg-bg-primary pt-16">
          <div className="container mx-auto px-6 py-8">
            <nav className="flex flex-col gap-6">
              <Link
                href={DEMO_HREF}
                onClick={() => setIsMobileMenuOpen(false)}
                className="font-sans text-lg text-text-secondary hover:text-text-primary transition-colors"
              >
                {t.header.demo}
              </Link>
              <Link
                href="/upload"
                onClick={() => setIsMobileMenuOpen(false)}
                className="font-sans text-lg text-text-secondary hover:text-text-primary transition-colors"
              >
                {t.header.startFree}
              </Link>
            </nav>

            <div className="mt-8 pt-8 border-t border-border-primary flex flex-col gap-4">
              <div className="flex justify-center">
                <LanguageSwitcher />
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
