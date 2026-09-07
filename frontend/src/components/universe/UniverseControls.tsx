"use client";

import { useState } from "react";
import { Menu, Moon, Sun, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";

interface UniverseControlsProps {
  current: "universe" | "nazmos" | "audit" | "company";
  theme: "dark" | "light";
  onToggleTheme: () => void;
  onNav: (target: "universe" | "nazmos" | "audit" | "company") => void;
}

/**
 * UniverseControls — minimal navigation + language + theme for the public home.
 * Dark/light are two first-class worlds; the switch flips the theme system
 * (`nazmos-theme` storage + the `.dark` class) and the shader follows.
 */
export function UniverseControls({ current, theme, onToggleTheme, onNav }: UniverseControlsProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const themeLabel = theme === "dark" ? t.universe.theme.toLight : t.universe.theme.toDark;

  const close = () => setOpen(false);
  const is = (k: string) => current === k;

  const items: { key: "universe" | "nazmos" | "audit" | "company"; label: string }[] = [
    { key: "universe", label: t.universe.nav.universe },
    { key: "nazmos", label: t.universe.nav.nazmos },
    { key: "audit", label: t.universe.nav.audit },
    { key: "company", label: t.universe.nav.about },
  ];

  return (
    <header className="absolute inset-x-0 top-0 z-50">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3 md:px-8">
        <button
          type="button"
          onClick={() => {
            onNav("universe");
            close();
          }}
          className="focus-ring flex items-center gap-3 rounded-md focus:outline-none"
          aria-label="Nazmak"
        >
          <span className="u-teal-bg h-4 w-4 rounded-full" />
          <span className="u-ink font-mono text-sm font-medium uppercase tracking-[0.2em]">
            Nazmak
          </span>
        </button>

        <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
          {items.map((it) => (
            <button
              key={it.key}
              type="button"
              onClick={() => onNav(it.key)}
              aria-current={is(it.key) ? "page" : undefined}
              className={cn(
                "focus-ring rounded-md px-3 py-2 text-sm transition-colors focus:outline-none",
                is(it.key) ? "u-teal" : "text-foreground/70 hover:text-foreground",
              )}
            >
              {it.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label={themeLabel}
            title={themeLabel}
            className="focus-ring inline-flex h-10 w-10 items-center justify-center rounded-lg text-foreground/70 transition-colors hover:text-foreground focus:outline-none"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <LanguageSwitcher className="hidden text-foreground/70 hover:text-foreground sm:flex" />
          {/* Mobile hamburger */}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="focus-ring inline-flex h-10 w-10 items-center justify-center rounded-lg text-foreground/90 hover:bg-card lg:hidden focus:outline-none"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="u-scrim border-b border-border/60 backdrop-blur-xl lg:hidden">
          <nav aria-label="Mobile" className="mx-auto max-w-7xl space-y-1 px-5 py-4">
            {items.map((it) => (
              <button
                key={it.key}
                type="button"
                onClick={() => {
                  onNav(it.key);
                  close();
                }}
                className="u-ink block w-full rounded-lg px-3 py-3 text-left text-base font-medium hover:bg-card"
              >
                {it.label}
              </button>
            ))}
            <div className="flex items-center gap-2 pt-3">
              <button
                type="button"
                onClick={() => {
                  onToggleTheme();
                  close();
                }}
                className="u-ink flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-card"
              >
                {theme === "dark" ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
                {themeLabel}
              </button>
              <LanguageSwitcher variant="compact" />
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}