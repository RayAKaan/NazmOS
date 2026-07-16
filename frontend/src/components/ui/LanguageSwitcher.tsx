"use client";

import { useI18n } from "@/lib/i18n";
import { Globe } from "lucide-react";
import { cn } from "@/lib/utils";

interface LanguageSwitcherProps {
  className?: string;
  variant?: "default" | "compact";
}

export function LanguageSwitcher({ className, variant = "default" }: LanguageSwitcherProps) {
  const { locale, setLocale } = useI18n();

  return (
    <button
      onClick={() => setLocale(locale === "en" ? "ar" : "en")}
      className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-lg transition-colors hover:bg-surface-hover",
        className
      )}
      title={locale === "en" ? "التبديل إلى العربية" : "Switch to English"}
    >
      <Globe className="w-4 h-4 text-text-muted" />
      {variant === "default" ? (
        <span className="text-sm font-medium">{locale === "en" ? "عربي" : "English"}</span>
      ) : (
        <span className="text-xs font-mono">{locale === "en" ? "AR" : "EN"}</span>
      )}
    </button>
  );
}
