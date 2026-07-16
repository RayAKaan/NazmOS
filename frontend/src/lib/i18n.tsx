"use client";

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";
import { en } from "./translations/en";
import { ar } from "./translations/ar";

export type Locale = "en" | "ar";

type Translations = Record<string, any>;

interface I18nContextType {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: Translations;
  dir: "ltr" | "rtl";
}

const I18nContext = createContext<I18nContextType | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>("en");

  useEffect(() => {
    const saved = localStorage.getItem("nazmos-locale") as Locale | null;
    if (saved && saved !== locale) {
      setLocale(saved);
      document.documentElement.dir = saved === "ar" ? "rtl" : "ltr";
      document.documentElement.lang = saved;
    }
  }, [locale]);

  const handleSetLocale = useCallback((l: Locale) => {
    setLocale(l);
    localStorage.setItem("nazmos-locale", l);
    document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
    document.documentElement.lang = l;
  }, []);

  const t = locale === "ar" ? ar : en;
  const dir = locale === "ar" ? "rtl" : "ltr";

  return (
    <I18nContext.Provider value={{ locale, setLocale: handleSetLocale, t, dir }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
