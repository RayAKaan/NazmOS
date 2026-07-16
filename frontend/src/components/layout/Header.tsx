'use client';

import * as React from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Menu, X, Package, TrendingUp, Percent, Sparkles, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useI18n } from '@/lib/i18n';
import { LanguageSwitcher } from '@/components/ui/LanguageSwitcher';

interface NavChild {
  title: string;
  href: string;
  icon?: typeof Package;
}

interface NavItemData {
  label: string;
  items?: NavChild[];
  href?: string;
}

function DropdownNav({ item }: { item: NavItemData }) {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <div 
      className="relative" 
      onMouseEnter={() => setIsOpen(true)} 
      onMouseLeave={() => setIsOpen(false)}
    >
      <button
        className="font-sans text-sm flex items-center gap-1 transition-colors duration-200 text-text-secondary hover:text-text-primary"
      >
        {item.label}
        <ChevronDown className={cn('w-3 h-3 transition-transform duration-200', isOpen && 'rotate-180')} />
      </button>

      {isOpen && item.items && (
        <div className="absolute top-full left-0 pt-2">
          <div className="bg-bg-secondary border border-border-primary p-1 min-w-[220px]">
            {item.items.map((child) => {
              const Icon = child.icon;
              return (
                <Link
                  key={child.title}
                  href={child.href}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-bg-tertiary transition-colors group"
                >
                  {Icon && (
                    <div className="w-8 h-8 bg-bg-tertiary flex items-center justify-center border border-border-primary">
                      <Icon className="w-4 h-4 text-accent-primary" />
                    </div>
                  )}
                  <span className="font-sans text-sm text-text-secondary group-hover:text-text-primary transition-colors">
                    {child.title}
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function SimpleNav({ item }: { item: NavItemData }) {
  return (
    <Link
      href={item.href || '/'}
      className="font-sans text-sm transition-colors duration-200 text-text-secondary hover:text-text-primary"
    >
      {item.label}
    </Link>
  );
}

export function Header() {
  const [isScrolled, setIsScrolled] = React.useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
  const { t } = useI18n();

  const NAV_ITEMS: NavItemData[] = [
    {
      label: t.header.product,
      items: [
        { title: t.header.inventory, href: '#inventory', icon: Package },
        { title: t.header.demandForecast, href: '#forecast', icon: TrendingUp },
        { title: t.header.pricing, href: '#pricing', icon: Percent },
        { title: t.header.aiAssistant, href: '#ai', icon: Sparkles },
      ],
    },
    {
      label: t.header.industries,
      items: [
        { title: t.header.supermarkets, href: '/industries/supermart' },
        { title: t.header.cafes, href: '/industries/cafe' },
        { title: t.header.retail, href: '/industries/retail' },
        { title: t.header.hotels, href: '/industries/hotel' },
      ],
    },
    { label: t.header.pricing, href: '/pricing' },
    { label: t.header.demo, href: '/demo' },
  ];

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
            <Link href="/" className="flex items-center gap-3">
              <div className="w-8 h-8 bg-bg-secondary border border-border-primary flex items-center justify-center">
                <span className="font-serif text-lg text-accent-primary">ن</span>
              </div>
              <span className="font-serif text-lg text-text-primary tracking-tight">NAZMOS</span>
            </Link>

            <nav className="hidden lg:flex items-center gap-8">
              {NAV_ITEMS.map((item, index) => (
                item.items ? (
                  <DropdownNav key={index} item={item} />
                ) : (
                  <SimpleNav key={index} item={item} />
                )
              ))}
            </nav>

            <div className="hidden lg:flex items-center gap-4">
              <LanguageSwitcher variant="compact" />
              <Link href="/login" className="font-sans text-sm text-text-secondary hover:text-text-primary transition-colors">
                {t.header.signIn}
              </Link>
              <Link href="/register">
                <Button size="sm">{t.header.startFree}</Button>
              </Link>
            </div>

            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="lg:hidden p-2 text-text-secondary hover:text-text-primary transition-colors"
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
              {NAV_ITEMS.map((item, index) => (
                <div key={index}>
                  {item.items ? (
                    <>
                      <span className="font-sans text-sm text-text-muted uppercase tracking-wider">{item.label}</span>
                      <div className="mt-3 flex flex-col gap-2">
                        {item.items.map((child) => {
                          const Icon = child.icon;
                          return (
                            <Link
                              key={child.title}
                              href={child.href}
                              onClick={() => setIsMobileMenuOpen(false)}
                              className="flex items-center gap-3 py-2 text-text-secondary hover:text-text-primary transition-colors"
                            >
                              {Icon && <Icon className="w-4 h-4 text-accent-primary" />}
                              <span className="font-sans text-base">{child.title}</span>
                            </Link>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <Link
                      href={item.href || '/'}
                      onClick={() => setIsMobileMenuOpen(false)}
                      className="font-sans text-lg text-text-secondary hover:text-text-primary transition-colors"
                    >
                      {item.label}
                    </Link>
                  )}
                </div>
              ))}
            </nav>

            <div className="mt-8 pt-8 border-t border-border-primary flex flex-col gap-4">
              <div className="flex justify-center">
                <LanguageSwitcher />
              </div>
              <Link href="/login" onClick={() => setIsMobileMenuOpen(false)} className="font-sans text-text-secondary hover:text-text-primary transition-colors">
                {t.header.signIn}
              </Link>
              <Link href="/register" onClick={() => setIsMobileMenuOpen(false)}>
                <Button size="lg" className="w-full">{t.header.startFree}</Button>
              </Link>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
